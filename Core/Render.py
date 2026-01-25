import subprocess
import tempfile
from PIL import ImageDraw
import pandas as pd
from PIL import Image
import os


#Export Handling using FFMPEG
def render_storyboard_ffmpeg(
    plan_file: str,
    history_df: pd.DataFrame,
    processed_df: pd.DataFrame,
    output_path: str = "Storyboard.mp4",
):
    """
    Renders a storyboard by:
    - Creating one frame per second
    - Drawing active mapping rectangles
    - Stitching frames into MP4 with ffmpeg
    """

    # Load base plan once
    base_img = Image.open(plan_file).convert("RGB")

    total_frames = processed_df["End Frame"].max() + 1

    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"Rendering {total_frames} frames to {tmpdir}")

        for frame_idx in range(total_frames):
            frame_img = base_img.copy()
            draw = ImageDraw.Draw(frame_img)

            # Find active rows for this frame
            active = processed_df[
                (processed_df["Start Frame"] <= frame_idx) &
                (processed_df["End Frame"] >= frame_idx)
            ]

            for _, row in active.iterrows():
                loc = row["Location"]

                # Lookup mapping
                match = history_df[history_df["Location"] == loc]
                if match.empty:
                    continue

                x1 = float(match.iloc[0]["X1"])
                y1 = float(match.iloc[0]["Y1"])
                x2 = float(match.iloc[0]["X2"])
                y2 = float(match.iloc[0]["Y2"])

                # Skip empty mappings
                if x1 == 0 and y1 == 0 and x2 == 0 and y2 == 0:
                    continue

                # Draw rectangle (red outline, semi-transparent fill not supported in RGB)
                draw.rectangle(
                    [(x1, y1), (x2, y2)],
                    outline="red",
                    width=4,
                )

            frame_path = os.path.join(tmpdir, f"frame_{frame_idx:05d}.png")
            frame_img.save(frame_path)

        # Call ffmpeg to stitch frames
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-framerate", "1",
            "-i", os.path.join(tmpdir, "frame_%05d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        print("Running ffmpeg...")
        subprocess.run(ffmpeg_cmd, check=True)

    print(f"Storyboard written to: {output_path}")