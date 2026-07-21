# %% [markdown]
# # CHRONOVISOR — Signal Processing Demo
# 
# This notebook demonstrates the signal analysis pipeline:
# 1. Generate or load EM signal data
# 2. FFT spectrum analysis
# 3. Harmonic and periodicity detection
# 4. Acoustic resonance analysis

# %%
import sys
sys.path.insert(0, '..')

import numpy as np
import matplotlib.pyplot as plt
from pipeline.signal_processor import SignalProcessor

proc = SignalProcessor(sample_rate=44100)

# %% [markdown]
# ## Generate Test Signal
# 
# Simulate an EM signal with harmonics — mimics resonance from underground cavities.

# %%
t = np.linspace(0, 1, 44100)
signal = (
    np.sin(2 * np.pi * 120 * t) * 0.5 +    # 120 Hz fundamental
    np.sin(2 * np.pi * 240 * t) * 0.3 +     # 2nd harmonic
    np.sin(2 * np.pi * 360 * t) * 0.15 +    # 3rd harmonic
    np.sin(2 * np.pi * 480 * t) * 0.08 +    # 4th harmonic
    np.random.normal(0, 0.05, len(t))         # noise
)

plt.figure(figsize=(12, 3))
plt.plot(t[:1000], signal[:1000], 'g-', linewidth=0.5)
plt.title('Signal (first 1000 samples)')
plt.xlabel('Time (s)')
plt.ylabel('Amplitude')
plt.grid(True, alpha=0.3)
plt.show()

# %% [markdown]
# ## FFT Spectrum Analysis

# %%
result = proc.analyze_spectrum(signal)

print(f"Sample count: {result['sample_count']}")
print(f"Duration: {result['duration_seconds']}s")
print(f"RMS amplitude: {result['rms_amplitude']}")
print(f"Spectral centroid: {result['spectral_centroid_hz']} Hz")
print(f"\nDominant frequencies:")
for f in result['dominant_frequencies']:
    print(f"  {f['frequency_hz']} Hz (magnitude={f['magnitude']:.6f})")

# Plot spectrum
freqs = result['spectrum']['frequencies']
mags = result['spectrum']['magnitudes']

plt.figure(figsize=(12, 4))
plt.fill_between(freqs, mags, alpha=0.3, color='#00ff88')
plt.plot(freqs, mags, 'g-', linewidth=0.5)
plt.title('Frequency Spectrum')
plt.xlabel('Frequency (Hz)')
plt.ylabel('Magnitude')
plt.xlim(0, 2000)
plt.grid(True, alpha=0.3)
plt.show()

# %% [markdown]
# ## Pattern Detection

# %%
print("Detected patterns:")
for p in result['patterns']:
    print(f"\n  Type: {p['type']}")
    for k, v in p.items():
        if k != 'type':
            print(f"    {k}: {v}")

# %% [markdown]
# ## Acoustic Resonance Analysis
# 
# Analyze resonance patterns that indicate underground cavities.

# %%
resonance = proc.analyze_acoustic_resonance(signal)
print(f"Cavity detected: {resonance['cavity_detected']}")
print(f"Resonance peaks: {len(resonance['resonance_peaks'])}")
print(f"\nInterpretation:")
for line in resonance['interpretation']:
    print(f"  {line}")

if resonance['cavity_indicators']:
    print(f"\nCavity indicators:")
    for c in resonance['cavity_indicators']:
        print(f"  {c['frequency_hz']} Hz (Q={c['q_factor']})")
