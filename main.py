#Argument Launch
import os
import argparse
from PIL import Image, UnidentifiedImageError
import pandas as pd
from Core.Render import render_storyboard_ffmpeg
from DesktopUI import run_ui


def argument_parser():
    
    p = argparse.ArgumentParser(
        description="Schedule-driven Storyboards"
    )

    p.add_argument(
        "Plan_image",
        help = "A high resolution image of your work plan."
    )

    p.add_argument(
        "Schedule_file",
        help = "Schedule to drive the story board animation. Must feature 'Location' field"
    )

    p.add_argument(
        "--Mapping_file",
        help="Optional previous mapping used",
        required=False
    )
    
    return p

def main():

    parser = argument_parser()
    args = parser.parse_args()

    #File Existence Checks
    plan_file = os.path.abspath(args.Plan_image)
    if not os.path.isfile(plan_file):
        raise FileNotFoundError(f"Plan file not found: {plan_file}")

    schedule_input = os.path.abspath(args.Schedule_file)
    if not os.path.exists(schedule_input):
        raise FileNotFoundError(f"Schedule input not found: {schedule_input}")

    schedule = pd.read_csv(schedule_input)
    if "Location" not in schedule.columns:
        raise ValueError("Schedule CSV missing required 'Location' column")

    if args.Mapping_file:
        history_path = os.path.abspath(args.Mapping_file)
        if not os.path.isfile(history_path):
            raise FileNotFoundError(f"Mapping file not found: {history_path}")

        history = pd.read_csv(history_path)
        if "Location" not in history.columns:
            raise ValueError("Mapping CSV missing required 'Location' column")
        
    else:
        #Create List of Unique Locations with empty Coordinate mapping 
        locations = schedule["Location"].dropna().unique()

        history = pd.DataFrame({
            "Location": locations,
            "X1": [0] * len(locations),
            "Y1": [0] * len(locations),
            "X2": [0] * len(locations),
            "Y2": [0] * len(locations),
            "Radius": [0] * len(locations),
        })

    #Check Image resolution
    minRes = 500
    def get_image_size(image_path: str) -> tuple[int, int]:
        try:
            with Image.open(image_path) as img:
                return img.size
        except UnidentifiedImageError:
            raise ValueError("Invalid or unsupported image file")
    
    width, height = get_image_size(plan_file)

    if width < minRes or height < minRes:
        raise ValueError(f"Image resolution too low. Minimum {minRes} x {minRes}")

    #Mapping check: Fits in Image
    for col in ["X1", "X2"]:
        if not history[col].between(0, width).all():
            raise ValueError(f"{col} out of bounds")

    for col in ["Y1", "Y2"]:
        if not history[col].between(0, height).all():
            raise ValueError(f"{col} out of bounds")

    #Evaluate schedule chronology logic
    for row in schedule.to_dict(orient="records"):
        start = row["Start"]
        end   = row["End"]
        if end < start:
            raise ValueError(
                f"Critical Error for {row['Activity']}: "
                f"End < Start ({end} < {start})"
            )

    #Converting times to keyframe values
    true_start = schedule["Start"].min()
    fps = 1

    #Schedule Preprocessing 
    processed = pd.DataFrame({
        "Activity": schedule["Activity"],
        "Start Frame": ((schedule["Start"] - true_start) * fps).astype(int),
        "End Frame": ((schedule["End"] - true_start) * fps).astype(int),
        "Location": schedule["Location"]
    })

    # UI Handoff

    def export_storyboard(history_df):
        render_storyboard_ffmpeg(
            plan_file=plan_file,
            history_df=history_df,
            processed_df=processed,
            output_path="Storyboard.mp4",
        )
        
  
    # Launch full UI with mapping + export hook
    run_ui(
    plan_image_path=plan_file,
    history_df=history,
    initial_mapping_path=args.Mapping_file,
    on_export=export_storyboard,
    )



if __name__ == "__main__":
    main()
