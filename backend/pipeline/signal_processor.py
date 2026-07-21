"""
CHRONOVISOR — Signal Processing Pipeline
Handles electromagnetic signal analysis, acoustic reconstruction,
and pattern detection from various data sources.
"""
import numpy as np
from typing import Optional
import json


class SignalProcessor:
    """Process and analyze electromagnetic and acoustic signals."""

    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate

    def analyze_spectrum(self, signal_data: np.ndarray, sample_rate: int = None) -> dict:
        """
        Run FFT analysis on signal data.
        Returns frequency spectrum, dominant frequencies, and pattern analysis.
        """
        if sample_rate:
            self.sample_rate = sample_rate
        n = len(signal_data)
        if n == 0:
            return {"error": "Empty signal"}

        # FFT
        fft_vals = np.fft.rfft(signal_data)
        magnitudes = np.abs(fft_vals) / n
        frequencies = np.fft.rfftfreq(n, 1.0 / self.sample_rate)

        # Find dominant frequencies
        top_indices = np.argsort(magnitudes)[-10:][::-1]
        dominant_freqs = [
            {
                "frequency_hz": round(float(frequencies[i]), 2),
                "magnitude": round(float(magnitudes[i]), 6),
                "period_seconds": round(1.0 / max(frequencies[i], 0.001), 4)
            }
            for i in top_indices if magnitudes[i] > 0.001
        ]

        # Spectral statistics
        spectral_centroid = float(np.sum(frequencies * magnitudes) / max(np.sum(magnitudes), 1e-10))
        spectral_bandwidth = float(np.sqrt(
            np.sum(((frequencies - spectral_centroid) ** 2) * magnitudes) / max(np.sum(magnitudes), 1e-10)
        ))

        # Pattern detection
        patterns = self._detect_patterns(signal_data, magnitudes, frequencies)

        return {
            "sample_count": n,
            "duration_seconds": round(n / self.sample_rate, 4),
            "dominant_frequencies": dominant_freqs,
            "spectral_centroid_hz": round(spectral_centroid, 2),
            "spectral_bandwidth_hz": round(spectral_bandwidth, 2),
            "rms_amplitude": round(float(np.sqrt(np.mean(signal_data ** 2))), 6),
            "peak_amplitude": round(float(np.max(np.abs(signal_data))), 6),
            "patterns": patterns,
            "spectrum": {
                "frequencies": frequencies[:500].tolist(),
                "magnitudes": magnitudes[:500].tolist()
            }
        }

    def _detect_patterns(self, signal: np.ndarray, magnitudes: np.ndarray, frequencies: np.ndarray) -> list:
        """Detect interesting patterns in the signal."""
        patterns = []

        # Harmonic detection
        if len(magnitudes) > 10:
            fundamental_idx = np.argmax(magnitudes[1:]) + 1  # skip DC
            fundamental_freq = frequencies[fundamental_idx]

            if fundamental_freq > 0:
                harmonics_found = 0
                for h in range(2, 8):
                    target_freq = fundamental_freq * h
                    freq_idx = np.argmin(np.abs(frequencies - target_freq))
                    if magnitudes[freq_idx] > magnitudes[fundamental_idx] * 0.1:
                        harmonics_found += 1

                if harmonics_found >= 2:
                    patterns.append({
                        "type": "harmonic_series",
                        "fundamental_hz": round(float(fundamental_freq), 2),
                        "harmonics_detected": harmonics_found,
                        "interpretation": "Natural resonant frequency detected — possible structural resonance"
                    })

        # Periodicity detection (autocorrelation)
        if len(signal) > 100:
            autocorr = np.correlate(signal[:1000], signal[:1000], mode='full')
            autocorr = autocorr[len(autocorr)//2:]
            autocorr = autocorr / max(autocorr[0], 1e-10)

            # Find peaks in autocorrelation
            peaks = []
            for i in range(2, len(autocorr) - 1):
                if autocorr[i] > autocorr[i-1] and autocorr[i] > autocorr[i+1] and autocorr[i] > 0.3:
                    peaks.append(i)

            if peaks:
                period_samples = peaks[0]
                period_seconds = period_samples / self.sample_rate
                patterns.append({
                    "type": "periodic_signal",
                    "period_seconds": round(period_seconds, 4),
                    "frequency_hz": round(1.0 / max(period_seconds, 0.0001), 2),
                    "confidence": round(float(autocorr[peaks[0]]), 4),
                    "interpretation": "Repeating pattern detected — cyclic environmental signal"
                })

        # Noise floor analysis
        noise_floor = np.percentile(magnitudes, 10)
        signal_peak = np.max(magnitudes)
        if signal_peak > 0:
            snr = 20 * np.log10(signal_peak / max(noise_floor, 1e-10))
            if snr > 20:
                patterns.append({
                    "type": "clear_signal",
                    "snr_db": round(float(snr), 2),
                    "interpretation": "Strong signal above noise floor — significant electromagnetic source"
                })

        return patterns

    def generate_em_field_map(
        self,
        readings: list,
        grid_size: int = 50
    ) -> dict:
        """
        Generate an electromagnetic field intensity map from real sensor readings.
        Each reading: {x, y, intensity}
        Returns a 2D grid of interpolated EM field values.
        Requires real sensor data — no synthetic fallback.
        """
        if not readings:
            return {
                "error": "No sensor readings provided. EM field mapping requires real data.",
                "required_format": [{"x": 0.5, "y": 0.3, "intensity": 0.8}],
                "sensor_suggestions": {
                    "rtl_sdr": "RTL-SDR dongle ($20) — EM spectrum analysis 24MHz-1.7GHz",
                    "hackrf": "HackRF One — wider spectrum coverage, bidirectional",
                    "sdr_play": "SDRplay RSP1a — high dynamic range EM receiver",
                    "magnetometer": "USB magnetometer — magnetic field intensity mapping"
                }
            }

        from scipy.interpolate import griddata

        points = np.array([[r["x"], r["y"]] for r in readings])
        values = np.array([r["intensity"] for r in readings])

        xi = np.linspace(0, 1, grid_size)
        yi = np.linspace(0, 1, grid_size)
        xi, yi = np.meshgrid(xi, yi)

        grid = griddata(points, values, (xi, yi), method='cubic', fill_value=0)

        # Find hotspots
        threshold = np.mean(grid) + 2 * np.std(grid)
        hotspot_mask = grid > threshold
        hotspot_count = int(np.sum(hotspot_mask))

        return {
            "grid_size": grid_size,
            "field_values": grid.tolist(),
            "hotspot_count": hotspot_count,
            "max_intensity": round(float(np.max(grid)), 4),
            "mean_intensity": round(float(np.mean(grid)), 4),
            "std_intensity": round(float(np.std(grid)), 4),
        }

    def analyze_acoustic_resonance(self, audio_data: np.ndarray) -> dict:
        """
        Analyze acoustic resonance patterns — useful for detecting
        cavities, voids, and structural features underground.
        """
        n = len(audio_data)
        if n < 1024:
            return {"error": "Signal too short for resonance analysis"}

        # Spectrogram
        from scipy.signal import spectrogram as scipy_spectrogram
        f, t, Sxx = scipy_spectrogram(
            audio_data,
            fs=self.sample_rate,
            nperseg=2048,
            noverlap=1024
        )

        # Find resonance peaks (frequencies with sustained energy)
        mean_spectrum = np.mean(Sxx, axis=1)
        peaks = []
        for i in range(1, len(mean_spectrum) - 1):
            if mean_spectrum[i] > mean_spectrum[i-1] and mean_spectrum[i] > mean_spectrum[i+1]:
                if mean_spectrum[i] > np.mean(mean_spectrum) + np.std(mean_spectrum):
                    peaks.append({
                        "frequency_hz": round(float(f[i]), 2),
                        "power_db": round(float(10 * np.log10(max(mean_spectrum[i], 1e-10))), 2),
                        "q_factor": round(float(f[i] / max(
                            f[min(i+1, len(f)-1)] - f[max(i-1, 0)], 0.1
                        )), 2)
                    })

        # High Q = sharp resonance = likely cavity
        cavity_indicators = [p for p in peaks if p["q_factor"] > 5]

        return {
            "duration_seconds": round(n / self.sample_rate, 2),
            "resonance_peaks": peaks[:20],
            "cavity_indicators": cavity_indicators,
            "cavity_detected": len(cavity_indicators) > 0,
            "interpretation": self._interpret_resonance(peaks, cavity_indicators)
        }

    def _interpret_resonance(self, peaks: list, cavities: list) -> list:
        """Interpret acoustic resonance findings."""
        interpretations = []
        if cavities:
            interpretations.append(
                f"Detected {len(cavities)} sharp resonance peak(s) — possible underground cavity or void"
            )
            for c in cavities[:3]:
                interpretations.append(
                    f"  Cavity resonance at {c['frequency_hz']}Hz (Q={c['q_factor']}) — "
                    f"estimated depth based on frequency"
                )
        if peaks:
            low_freq = [p for p in peaks if p["frequency_hz"] < 200]
            if low_freq:
                interpretations.append(
                    "Low-frequency resonance detected — possible large-scale geological feature"
                )
        return interpretations if interpretations else ["No significant resonance patterns detected"]


