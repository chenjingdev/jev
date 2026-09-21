"""Run the two-stage Jev attention experiment on a supplied desktop screenshot."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from attention import (ask_jev, coarse_candidates, detail_candidates, fastsam_observe,
                       padded_box, region_by_id)


GOAL = "Click the message composition input in the KakaoTalk chat room titled '점채널'."


def font(size=24):
    path = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
    return ImageFont.truetype(str(path), size) if path.is_file() else ImageFont.load_default()


def top_probabilities(answer, count=8):
    return sorted(answer["probabilities"].items(), key=lambda item: item[1], reverse=True)[:count]


def draw_overlay(image, coarse, detail, coarse_pick, detail_pick, focus, target):
    out = image.convert("RGBA")
    draw = ImageDraw.Draw(out, "RGBA")
    for region in coarse:
        color = (225, 145, 30, 255) if region.id == coarse_pick else (50, 115, 180, 150)
        draw.rectangle(region.box, outline=color, width=5 if region.id == coarse_pick else 2)
        draw.text((region.box[0] + 4, region.box[1] + 4), region.id, fill=color, font=font(22))
    draw.rectangle(focus, outline=(245, 190, 30, 255), width=5)
    for region in detail:
        color = (220, 40, 55, 255) if region.id == detail_pick else (38, 145, 85, 155)
        if region.polygon:
            draw.line(region.polygon + [region.polygon[0]], fill=color, width=6 if region.id == detail_pick else 2)
        else:
            draw.rectangle(region.box, outline=color, width=6 if region.id == detail_pick else 2)
        if region.id == detail_pick:
            draw.text((region.box[0] + 4, region.box[1] + 4), region.id, fill=color, font=font(24))
    x, y = target
    draw.ellipse((x - 15, y - 15, x + 15, y + 15), fill=(255, 25, 35, 220), outline="white", width=4)
    return out


def quartz_target_window(width, height, display_x=-2560, display_y=0):
    import Quartz
    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    for item in Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID):
        if item.get("kCGWindowOwnerName") != "카카오톡" or item.get("kCGWindowName") != "점채널":
            continue
        bounds = item["kCGWindowBounds"]
        x, y, w, h = (float(bounds[k]) for k in ("X", "Y", "Width", "Height"))
        return (max(0, x - display_x), max(0, y - display_y),
                min(width, x - display_x + w), min(height, y - display_y + h))
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", default="jev-latest")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    image = Image.open(args.image).convert("RGB")
    width, height = image.size
    regions, words, vision_s = fastsam_observe(args.image, HERE / "models/FastSAM-s.pt")

    coarse = coarse_candidates(regions, width, height)
    coarse_state = {
        "goal": GOAL,
        "screen": {"width": width, "height": height},
        "regions": [region.state(width, height) for region in coarse],
    }
    coarse_answer = ask_jev(
        coarse_state, coarse,
        instructions=(
            "Choose the smallest self-contained region that contains the KakaoTalk conversation "
            "whose room title is exactly '점채널'. Prefer a region containing that exact observed "
            "title and its messages. Avoid the room list, unrelated chats, and the broadcast page."
        ),
        presence="Does any supplied region contain the KakaoTalk conversation titled exactly '점채널'?",
        model=args.model,
    )
    coarse_pick = region_by_id(coarse, coarse_answer["choice"])
    focus = padded_box(coarse_pick.box, width, height)

    detail = detail_candidates(regions, focus, width, height)
    detail_state = {
        "goal": GOAL,
        "selected_chat_region": coarse_pick.state(width, height),
        "candidate_subregions": [region.state(width, height) for region in detail],
    }
    detail_answer = ask_jev(
        detail_state, detail,
        instructions=(
            "Choose the subregion that is the message composition input field for the selected "
            "KakaoTalk room. Prefer the region whose observed text is exactly or approximately "
            "'메시지 입력'. Do not choose a message bubble, room title, toolbar, or send button."
        ),
        presence="Does any candidate subregion contain the message composition input field text '메시지 입력'?",
        model=args.model,
    )
    target_region = region_by_id(detail, detail_answer["choice"])
    x0, y0, x1, y1 = target_region.box
    target = (round((x0 + x1) / 2), round((y0 + y1) / 2))

    expected_window = quartz_target_window(width, height)
    inside_expected = None if expected_window is None else (
        expected_window[0] <= target[0] <= expected_window[2] and
        expected_window[1] <= target[1] <= expected_window[3] and
        target[1] >= expected_window[3] - 150
    )
    overlay = draw_overlay(image, coarse, detail, coarse_answer["choice"],
                           detail_answer["choice"], focus, target)
    overlay.save(args.out / "attention-result.png")

    result = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "goal": GOAL,
        "image": {"width": width, "height": height},
        "vision": {"model": "FastSAM-s", "inference_s": round(vision_s, 3),
                   "raw_masks": len(regions), "coarse_candidates": len(coarse),
                   "detail_candidates": len(detail), "ocr_words": len(words)},
        "coarse": {**coarse_answer, "selected": coarse_pick.state(width, height),
                   "top_probabilities": top_probabilities(coarse_answer)},
        "detail": {**detail_answer, "selected": target_region.state(width, height),
                   "top_probabilities": top_probabilities(detail_answer)},
        "target": {"screen_xy": list(target), "inside_expected_input_band": inside_expected,
                   "validation_window_found": expected_window is not None},
    }
    (args.out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
