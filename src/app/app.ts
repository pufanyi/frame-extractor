import { Component, ElementRef, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';

interface ExtractedFrame {
  id: string;
  time: number;
  width: number;
  height: number;
  dataUrl: string;
  selected: boolean;
}

const ALLOWED_EXTENSIONS = new Set(['.mp4', '.mov', '.webm', '.mkv']);
const MAX_FRAME_COUNT = 40;
const MAX_EXPORT_FRAMES = 20;
const SEEK_EPSILON_SECONDS = 0.05;
const SEEK_TIMEOUT_MS = 8000;

@Component({
  selector: 'app-root',
  imports: [FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App {
  @ViewChild('videoInput') private videoInput?: ElementRef<HTMLInputElement>;

  readonly maxFrameCount = MAX_FRAME_COUNT;
  readonly maxExportFrames = MAX_EXPORT_FRAMES;
  readonly acceptTypes = '.mp4,.mov,.webm,.mkv';

  frameCountInput = 10;
  statusMessage = '';
  errorMessage = '';
  isExtracting = false;
  isExporting = false;
  frames: ExtractedFrame[] = [];

  get selectedCount(): number {
    return this.frames.filter((frame) => frame.selected).length;
  }

  get canExport(): boolean {
    return this.selectedCount > 0 && !this.isExtracting && !this.isExporting;
  }

  async onExtract(event: Event): Promise<void> {
    event.preventDefault();
    if (this.isExtracting || this.isExporting) {
      return;
    }

    const file = this.videoInput?.nativeElement.files?.[0];
    if (!file) {
      this.fail('Please select a video file.');
      return;
    }

    const ext = this.getExtension(file.name);
    if (!ALLOWED_EXTENSIONS.has(ext)) {
      this.fail(`Unsupported format "${ext || '(none)'}". Allowed: .mp4, .mov, .webm, .mkv`);
      return;
    }

    const requestedCount = Math.floor(this.frameCountInput);
    this.frameCountInput = requestedCount;
    if (!Number.isFinite(requestedCount) || requestedCount < 1) {
      this.fail('Number of frames must be a positive integer.');
      return;
    }
    if (requestedCount > this.maxFrameCount) {
      this.fail(`Please use ${this.maxFrameCount} frames or fewer for browser stability.`);
      return;
    }

    this.isExtracting = true;
    this.isExporting = false;
    this.errorMessage = '';
    this.frames = [];
    this.statusMessage = 'Loading video metadata...';

    try {
      const frames = await this.extractFrames(file, requestedCount);
      if (frames.length === 0) {
        throw new Error('Failed to extract frames from this video.');
      }
      this.frames = frames;
      this.statusMessage = `Extracted ${frames.length} frames. Select frames and export SVG.`;
    } catch (error: unknown) {
      this.fail(this.toErrorMessage(error));
    } finally {
      this.isExtracting = false;
    }
  }

  setFrameSelection(frame: ExtractedFrame, event: Event): void {
    const input = event.target as HTMLInputElement | null;
    frame.selected = Boolean(input?.checked);
  }

  async exportFilmstrip(): Promise<void> {
    if (!this.canExport) {
      return;
    }

    const selectedFrames = this.frames.filter((frame) => frame.selected);
    if (selectedFrames.length > this.maxExportFrames) {
      this.fail(`Too many selected frames (max ${this.maxExportFrames}).`);
      return;
    }

    this.errorMessage = '';
    this.isExporting = true;
    this.statusMessage = 'Generating filmstrip SVG...';

    try {
      const svg = this.buildFilmstripSvg(selectedFrames);
      this.downloadText(svg, 'filmstrip.svg', 'image/svg+xml;charset=utf-8');
      this.statusMessage = `Exported filmstrip.svg with ${selectedFrames.length} frame${selectedFrames.length === 1 ? '' : 's'}.`;
    } catch (error: unknown) {
      this.fail(this.toErrorMessage(error));
    } finally {
      this.isExporting = false;
    }
  }

  formatTimestamp(seconds: number): string {
    if (!Number.isFinite(seconds) || seconds < 0) {
      return '00:00.000';
    }
    const totalMs = Math.round(seconds * 1000);
    const minutes = Math.floor(totalMs / 60000);
    const secs = Math.floor((totalMs % 60000) / 1000);
    const ms = totalMs % 1000;
    return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${String(ms).padStart(3, '0')}`;
  }

  private async extractFrames(file: File, count: number): Promise<ExtractedFrame[]> {
    const objectUrl = URL.createObjectURL(file);
    const video = document.createElement('video');
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');

    if (!context) {
      URL.revokeObjectURL(objectUrl);
      throw new Error('Unable to initialize canvas rendering context.');
    }

    video.preload = 'auto';
    video.muted = true;
    video.playsInline = true;
    video.src = objectUrl;
    video.load();

    try {
      await this.waitForLoadedMetadata(video);
      await this.waitForLoadedData(video);

      const duration = video.duration;
      const width = video.videoWidth;
      const height = video.videoHeight;
      if (!Number.isFinite(duration) || duration <= 0 || width < 1 || height < 1) {
        throw new Error('Video has no readable frames.');
      }

      canvas.width = width;
      canvas.height = height;

      const sampleTimes = this.buildSampleTimes(duration, count);
      const extracted: ExtractedFrame[] = [];

      for (let i = 0; i < sampleTimes.length; i += 1) {
        const time = sampleTimes[i];
        this.statusMessage = `Extracting frames... (${i + 1}/${sampleTimes.length})`;
        await this.seekVideo(video, time);
        context.drawImage(video, 0, 0, width, height);

        extracted.push({
          id: `frame_${String(i).padStart(3, '0')}`,
          time,
          width,
          height,
          dataUrl: canvas.toDataURL('image/jpeg', 0.92),
          selected: false
        });
      }

      return extracted;
    } catch (error: unknown) {
      throw new Error(this.toErrorMessage(error));
    } finally {
      URL.revokeObjectURL(objectUrl);
      video.removeAttribute('src');
      video.load();
    }
  }

  private buildSampleTimes(duration: number, count: number): number[] {
    if (count === 1) {
      return [0];
    }
    const maxSeekable = Math.max(0, duration - SEEK_EPSILON_SECONDS);
    return Array.from({ length: count }, (_, i) => (maxSeekable * i) / (count - 1));
  }

  private waitForLoadedMetadata(video: HTMLVideoElement): Promise<void> {
    if (video.readyState >= HTMLMediaElement.HAVE_METADATA) {
      return Promise.resolve();
    }
    return new Promise<void>((resolve, reject) => {
      const onLoaded = (): void => {
        cleanup();
        resolve();
      };
      const onError = (): void => {
        cleanup();
        reject(new Error('Video file could not be opened. It may be corrupted or unsupported.'));
      };
      const cleanup = (): void => {
        video.removeEventListener('loadedmetadata', onLoaded);
        video.removeEventListener('error', onError);
      };

      video.addEventListener('loadedmetadata', onLoaded);
      video.addEventListener('error', onError);
    });
  }

  private waitForLoadedData(video: HTMLVideoElement): Promise<void> {
    if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
      return Promise.resolve();
    }
    return new Promise<void>((resolve, reject) => {
      const onLoaded = (): void => {
        cleanup();
        resolve();
      };
      const onError = (): void => {
        cleanup();
        reject(new Error('Video frame data could not be decoded.'));
      };
      const cleanup = (): void => {
        video.removeEventListener('loadeddata', onLoaded);
        video.removeEventListener('error', onError);
      };

      video.addEventListener('loadeddata', onLoaded);
      video.addEventListener('error', onError);
    });
  }

  private seekVideo(video: HTMLVideoElement, time: number): Promise<void> {
    const clampedTime = Math.max(
      0,
      Math.min(time, Math.max(0, (Number.isFinite(video.duration) ? video.duration : time) - SEEK_EPSILON_SECONDS))
    );

    return new Promise<void>((resolve, reject) => {
      if (Math.abs(video.currentTime - clampedTime) < 0.0005) {
        requestAnimationFrame(() => resolve());
        return;
      }

      let timeoutId: ReturnType<typeof setTimeout> | undefined;

      const onSeeked = (): void => {
        cleanup();
        resolve();
      };
      const onError = (): void => {
        cleanup();
        reject(new Error('Video seek failed while extracting frames.'));
      };
      const onTimeout = (): void => {
        cleanup();
        reject(new Error('Timed out while seeking video frames.'));
      };
      const cleanup = (): void => {
        if (timeoutId) {
          clearTimeout(timeoutId);
        }
        video.removeEventListener('seeked', onSeeked);
        video.removeEventListener('error', onError);
      };

      video.addEventListener('seeked', onSeeked);
      video.addEventListener('error', onError);
      timeoutId = setTimeout(onTimeout, SEEK_TIMEOUT_MS);
      video.currentTime = clampedTime;
    });
  }

  private buildFilmstripSvg(selectedFrames: ExtractedFrame[]): string {
    if (selectedFrames.length < 1) {
      throw new Error('No frames selected.');
    }

    const frameDisplayHeight = 200;
    const sample = selectedFrames[0];
    const frameDisplayWidth = Math.max(120, Math.round((frameDisplayHeight * sample.width) / sample.height));

    const padding = 12;
    const perfRadius = 8;
    const perfMargin = 18;
    const labelHeight = 24;
    const stripHeight = frameDisplayHeight + 2 * padding + 2 * perfMargin + 2 * perfRadius + labelHeight;
    const cellWidth = frameDisplayWidth + 2 * padding;
    const totalWidth = cellWidth * selectedFrames.length;
    const imageY = perfMargin + perfRadius + padding;
    const labelY = imageY + frameDisplayHeight + 17;

    const parts: string[] = [];
    parts.push('<?xml version="1.0" encoding="UTF-8"?>');
    parts.push(
      `<svg xmlns="http://www.w3.org/2000/svg" width="${totalWidth}" height="${stripHeight}" viewBox="0 0 ${totalWidth} ${stripHeight}">`
    );
    parts.push(`<rect width="${totalWidth}" height="${stripHeight}" rx="10" fill="#1c2429"/>`);

    selectedFrames.forEach((frame, i) => {
      const xOffset = i * cellWidth;
      const centerX = xOffset + cellWidth / 2;
      const frameX = xOffset + padding;

      parts.push(`<circle cx="${centerX}" cy="${perfMargin}" r="${perfRadius}" fill="#34424a"/>`);
      parts.push(`<circle cx="${centerX}" cy="${stripHeight - perfMargin}" r="${perfRadius}" fill="#34424a"/>`);
      parts.push(
        `<rect x="${frameX - 2}" y="${imageY - 2}" width="${frameDisplayWidth + 4}" height="${frameDisplayHeight + 4}" rx="3" fill="#42545f"/>`
      );
      parts.push(
        `<image href="${frame.dataUrl}" x="${frameX}" y="${imageY}" width="${frameDisplayWidth}" height="${frameDisplayHeight}" preserveAspectRatio="xMidYMid slice"/>`
      );
      parts.push(
        `<text x="${centerX}" y="${labelY}" fill="#c9d4da" text-anchor="middle" font-family="Arial, sans-serif" font-size="11">${this.formatTimestamp(frame.time)}</text>`
      );
    });

    parts.push('</svg>');
    return parts.join('\n');
  }

  private downloadText(content: string, filename: string, mimeType: string): void {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  private getExtension(filename: string): string {
    const idx = filename.lastIndexOf('.');
    return idx >= 0 ? filename.slice(idx).toLowerCase() : '';
  }

  private fail(message: string): void {
    this.errorMessage = message;
    this.statusMessage = '';
  }

  private toErrorMessage(error: unknown): string {
    if (error instanceof Error && error.message) {
      return error.message;
    }
    return 'Unexpected error.';
  }
}
