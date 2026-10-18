export interface MediaItem {
  id: string;
  type: 'image' | 'video' | 'audio';
  title: string;
  description: string;
  alt: string;
  tags: string[];
  featured: boolean;
  order: number;
  original: string;
  src: string;
  poster: string;
  variants: { width: number; src: string }[];
  width?: number;
  height?: number;
  duration?: number;
  captions?: string;
  transcript?: string;
  preview?: string;
  focalPoint?: string;
}
