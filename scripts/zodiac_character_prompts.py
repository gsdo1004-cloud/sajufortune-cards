"""Copyright-independent Korean zodiac character bible and protected layout zones."""
from scripts.zodiac_style_rotation import style_for_day
TRAITS={
"rat":"tiny cream-and-caramel round mouse, pink ears, friendly sparkling eyes",
"ox":"gentle golden-brown ox, small horns, cream muzzle, kind eyes",
"tiger":"fluffy golden tiger cub, rounded dark stripes and cream cheeks",
"rabbit":"snow-white rabbit, blush pink ears and lavender scarf",
"dragon":"benevolent serpentine East Asian dragon, flowing whiskers, antler-like horns, jade teal scales, NO wings",
"snake":"adorable pastel mint-green baby snake, round face and tiny smile",
"horse":"warm chestnut pony, honey mane and rounded muzzle",
"goat":"plush ivory goat, little curved horns and peach cheeks",
"monkey":"cheerful apricot young monkey, cream face and rounded paws",
"rooster":"small amber rooster with ruby red comb and short fluffy tail",
"dog":"friendly sandy puppy, floppy ears and dark brown nose",
"pig":"joyful rosy piglet, round cheeks and little button nose",
}
STEMS=("01_표지","02_띠별A","03_띠별B","04_띠별C","05_띠별D","06_12띠요약")
NAMES=tuple(TRAITS)
SUBJECTS=(NAMES,NAMES[:3],NAMES[3:6],NAMES[6:9],NAMES[9:12],NAMES)
# These zones are an authored scene composition contract, NOT actual face detection.
PROTECTED=(((.09,.27,.91,.77),),((.02,.12,.30,.84),),((.02,.12,.30,.84),),
           ((.02,.12,.30,.84),),((.02,.12,.30,.84),),())
PLACEMENT=(
"show all twelve complete friendly animals in center-middle, keep top 22% and bottom 14% free",
"stack all three animal faces ONLY inside leftmost 28%; keep right 70% empty",
"stack all three animal faces ONLY inside leftmost 28%; keep right 70% empty",
"stack all three animal faces ONLY inside leftmost 28%; keep right 70% empty",
"stack all three animal faces ONLY inside leftmost 28%; keep right 70% empty",
"small decorative zodiac symbols only outside the central two-column grid",
)
NEGATIVE="text, captions, watermark, letters, numbers, logos, western dragon, dragon wings, scary snake or mouse, cropped face, extra limbs, duplicated animal, copyrighted mascot likeness"
def protected_boxes(stem,w,h):
    i=STEMS.index(stem)
    return [tuple(round(v*(w if j%2==0 else h)) for j,v in enumerate(b)) for b in PROTECTED[i]]
def prompt_for(day,stem,medium="card"):
    i=STEMS.index(stem);sty=style_for_day(day)
    names="; ".join(f"{n}: {TRAITS[n]}" for n in SUBJECTS[i])
    return (f"EXACTLY {len(SUBJECTS[i])} distinct ORIGINAL Korean zodiac mascots: {names}. "
            f"Illustration {sty['id']} {sty['name']}, {sty['prompt']}. "
            "Maintain identical character facial features, markings and species colors between all scenes. "
            f"9:16 portrait {medium} composition: {PLACEMENT[i]}. "
            "Traditional Korean auspicious scenery, sophisticated cheerful colors, full faces. "
            f"STRICT NEGATIVE: {NEGATIVE}.")
