"""Real-time Fast Fourier Transform (FFT) spectrum analyzer and waveform engine."""

from __future__ import annotations

import math


class AudioFFTEngine:
    """Computes frequency spectrum magnitudes across logarithmic frequency bands with perceptual weighting and AGC."""

    NUM_BANDS = 32

    def __init__(self, sample_rate: int = 48000, window_size: int = 1024) -> None:
        self.sample_rate = sample_rate
        self.window_size = window_size
        self._hanning_window = [
            0.5 * (1.0 - math.cos(2.0 * math.pi * n / (window_size - 1)))
            for n in range(window_size)
        ]
        self.peaks: list[float] = [0.0] * self.NUM_BANDS
        self.peak_decay_rate = 0.035  # Smooth falloff rate per frame
        self.running_max: float = 30.0  # Dynamic Automatic Gain Control (AGC) ceiling

        # Precompute logarithmic band edge boundaries (35 Hz to 16 kHz)
        f_min, f_max = 35.0, 16000.0
        edges = [
            f_min * math.pow(f_max / f_min, i / self.NUM_BANDS) for i in range(self.NUM_BANDS + 1)
        ]
        self.bin_edges = [max(0.5, f * window_size / sample_rate) for f in edges]

        # Perceptual equal-loudness weighting across 32 bands
        # Treble and presence receive gentle psychoacoustic compensation for lively response
        self.freq_weights = [
            math.pow(1.0 + (i / self.NUM_BANDS) * 3.2, 0.7) for i in range(self.NUM_BANDS)
        ]

    def process_pcm(self, samples: list[float]) -> tuple[list[float], list[float]]:
        """
        Processes PCM samples into:
        1. Band magnitudes (normalized 0.0 to 1.0, 32 bands)
        2. Peak-decay values (normalized 0.0 to 1.0)
        """
        n = min(len(samples), self.window_size)
        if n < 16:
            # Decay existing peaks and return zeros
            self.peaks = [max(0.0, p - self.peak_decay_rate) for p in self.peaks]
            return [0.0] * self.NUM_BANDS, list(self.peaks)

        # Pad or slice to exact window size
        in_buf = samples[-self.window_size :]
        if len(in_buf) < self.window_size:
            in_buf = [0.0] * (self.window_size - len(in_buf)) + in_buf

        # Windowing
        windowed = [in_buf[i] * self._hanning_window[i] for i in range(self.window_size)]

        # Try fast numpy FFT if available, else approximate discrete DFT filter bank
        try:
            import numpy as np

            fft_res = np.abs(np.fft.rfft(windowed))
            mags = [float(x) for x in fft_res]
        except ImportError:
            mags = self._simple_dft_bands(windowed)

        # Continuous fractional bin grouping into 32 bands
        band_values = self._group_log_bands(mags)

        # Update peak-decay trackers
        for i in range(self.NUM_BANDS):
            val = band_values[i]
            if val > self.peaks[i]:
                self.peaks[i] = val
            else:
                self.peaks[i] = max(0.0, self.peaks[i] - self.peak_decay_rate)

        return band_values, list(self.peaks)

    def _group_log_bands(self, fft_magnitudes: list[float]) -> list[float]:
        """Groups raw linear FFT bins into 32 distinct bands using continuous fractional bin integration."""
        if not fft_magnitudes:
            return [0.0] * self.NUM_BANDS

        total_bins = len(fft_magnitudes)
        raw_bands: list[float] = []

        for b in range(self.NUM_BANDS):
            b_start = self.bin_edges[b]
            b_end = self.bin_edges[b + 1]

            i_start = int(math.floor(b_start))
            i_end = int(math.ceil(b_end))
            if i_end <= i_start:
                i_end = i_start + 1

            total_val = 0.0
            total_w = 0.0
            for idx in range(i_start, min(total_bins, i_end)):
                overlap = min(b_end, idx + 1) - max(b_start, idx)
                if overlap > 0:
                    total_val += fft_magnitudes[idx] * overlap
                    total_w += overlap

            avg = (total_val / total_w) if total_w > 0 else 0.0
            raw_bands.append(avg * self.freq_weights[b])

        # Automatic Gain Control (AGC) tracking peak dynamics
        frame_max = max(raw_bands) if raw_bands else 1.0
        self.running_max = max(frame_max, self.running_max * 0.985, 15.0)

        # True Studio dBFS logarithmic normalization (-60 dBFS floor to 0 dBFS ceiling)
        band_values: list[float] = []
        for val in raw_bands:
            norm = max(1e-4, val / max(1e-6, self.running_max))
            # True acoustic power in decibels: 20 * log10(norm)
            db = 20.0 * math.log10(norm)
            # Map [-60 dB, 0 dB] linearly to height fraction [0.0, 1.0]
            height_frac = (db + 60.0) / 60.0
            band_values.append(max(0.0, min(1.0, height_frac)))

        return band_values

    def _simple_dft_bands(self, samples: list[float]) -> list[float]:
        """Pure-Python fallback filter bank when NumPy is not installed."""
        bands = []
        n = len(samples)
        for k in range(min(128, n // 2)):
            real = 0.0
            imag = 0.0
            for t in range(0, n, 4):  # Subsample by 4 for speed
                ang = 2.0 * math.pi * k * t / n
                real += samples[t] * math.cos(ang)
                imag -= samples[t] * math.sin(ang)
            bands.append(math.sqrt(real * real + imag * imag))
        return bands
