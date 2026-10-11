"""Original procedural instrumental compositions. No samples or external melodies.
Source and generated recordings dedicated to CC0-1.0. Rebuild with Python stdlib.
"""
import math
import random
import struct
import wave
from pathlib import Path

RATE = 24000
TRACKS = {
    'slow-morning': (76, [[57, 60, 64, 67], [53, 57, 60, 64], [55, 59, 62, 67], [52, 55, 59, 62]], 0),
    'little-weekend': (104, [[60, 64, 67, 71], [57, 60, 64, 69], [53, 57, 60, 65], [55, 59, 62, 67]], 1),
    'after-hours': (88, [[50, 53, 57, 60], [58, 62, 65, 69], [53, 57, 60, 64], [48, 52, 55, 59]], 2),
}


def compose(name, bpm, chords, style, destination):
    beat = 60 / bpm; duration = 16 * beat
    samples = [0.0] * int(duration * RATE)
    rng = random.Random(name)
    def tone(start, length, midi, level, pluck=True):
        frequency = 440 * 2 ** ((midi - 69) / 12)
        first = round(start * RATE)
        for n in range(min(round(length * RATE), len(samples) - first)):
            t = n / RATE
            envelope = min(t / .015, 1) * (math.exp(-t * 2.3) if pluck else min((length-t)/.25, 1) * .55)
            value = math.sin(2 * math.pi * frequency * t) + .2 * math.sin(4 * math.pi * frequency * t)
            samples[first+n] += value * envelope * level
    for bar, chord in enumerate(chords):
        start = bar * 4 * beat
        for midi in chord:
            tone(start, 4 * beat, midi, .035, False)
        tone(start, 2 * beat, chord[0]-12, .095)
        for step in range(8):
            midi = chord[(step * 3 + bar) % 4] + (12 if style == 1 else 0)
            tone(start + step * beat / 2, beat * .9, midi, .055 if style != 2 else .04)
        if style == 1:
            for step in range(4):
                first = round((start + step * beat) * RATE)
                for n in range(min(int(.12 * RATE), len(samples)-first)):
                    t=n/RATE
                    samples[first+n] += math.sin(2*math.pi*(55*t+3*(1-math.exp(-t*35))))*math.exp(-t*30)*.11
            for step in range(8):
                first=round((start+step*beat/2)*RATE)
                for n in range(min(int(.06*RATE),len(samples)-first)):
                    samples[first+n] += rng.uniform(-1,1)*math.exp(-n/RATE*85)*.018
    peak=max(abs(v) for v in samples) or 1
    frames=bytearray()
    for i,v in enumerate(samples):
        t=i/RATE
        fade=min(t/.03,(duration-t)/.06,1)
        value=int(max(-1,min(1,v/peak*.75*fade))*32767)
        frames.extend(struct.pack('<hh',value,value))
    with wave.open(str(destination / (name+'.wav')),'wb') as f:
        f.setnchannels(2);f.setsampwidth(2);f.setframerate(RATE);f.writeframes(frames)


if __name__ == '__main__':
    destination=Path(__file__).resolve().parent.parent/'resources'/'music';destination.mkdir(exist_ok=True)
    for name, (bpm,chords,style) in TRACKS.items():
        compose(name,bpm,chords,style,destination)
    print('Original instrumental library: 3 tracks generated.')
