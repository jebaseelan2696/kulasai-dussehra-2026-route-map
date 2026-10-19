"""Convert the recorded .webm clips to .mp4 for sharing.

H.264 + AAC-free (no audio) baseline MP4 plays on phones and in WhatsApp,
which will not preview webm. Run after record_clips.py:

    python tools/convert_clips.py
"""
import os, subprocess, sys, imageio_ffmpeg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'clips')
FF = imageio_ffmpeg.get_ffmpeg_exe()

def main():
    names = sorted(f for f in os.listdir(SRC) if f.endswith('.webm'))
    if not names:
        sys.exit('no .webm files in clips/')
    ok = 0
    for n in names:
        src = os.path.join(SRC, n)
        dst = os.path.join(SRC, n[:-5] + '.mp4')
        cmd = [FF, '-y', '-loglevel', 'error', '-i', src,
               '-c:v', 'libx264', '-profile:v', 'baseline', '-level', '3.1',
               '-pix_fmt', 'yuv420p', '-crf', '26', '-preset', 'medium',
               '-movflags', '+faststart', '-an',
               # even dimensions are required by yuv420p
               '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
               dst]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            print('FAILED %s\n%s' % (n, r.stderr.strip()[:300]))
            continue
        ok += 1
        print('%-70s %4d KB' % (os.path.basename(dst), os.path.getsize(dst) // 1024))
    print('\n%d of %d converted' % (ok, len(names)))

if __name__ == '__main__':
    main()
