import pyperclip

commands = [
    "!addhistory luigi_is_better deaths ",
    "!addhistory luigi_is_better advancements ",
    "!addhistory luigi_is_better playtime ",

    "!addhistory sblujay deaths ",
    "!addhistory sblujay advancements ",
    "!addhistory sblujay playtime ",

    "!addhistory kazzpyr deaths ",
    "!addhistory kazzpyr advancements ",
    "!addhistory kazzpyr playtime ",

    "!addhistory bobbilby deaths ",
    "!addhistory bobbilby advancements ",
    "!addhistory bobbilby playtime ",

    "!addhistory wizardcat1000 deaths ",
    "!addhistory wizardcat1000 advancements ",
    "!addhistory wizardcat1000 playtime ",

    "!addhistory ih8tk deaths ",
    "!addhistory ih8tk advancements ",
    "!addhistory ih8tk playtime ",

    "!addhistory salmon5117_73205 deaths ",
    "!addhistory salmon5117_73205 advancements ",
    "!addhistory salmon5117_73205 playtime ",

    "!addhistory frogloverender deaths ",
    "!addhistory frogloverender advancements ",
    "!addhistory frogloverender playtime ",

    "!addhistory sweatshirtboi16 deaths ",
    "!addhistory sweatshirtboi16 advancements ",
    "!addhistory sweatshirtboi16 playtime ",

    "!addhistory mindjames_93738 ",
    "!addhistory mindjames_93738 advancements ",
    "!addhistory mindjames_93738 playtime ",

    "!addhistory car248. deaths ",
    "!addhistory car248. advancements ",
    "!addhistory car248. playtime ",

    "!addhistory ctslayer. deaths ",
    "!addhistory ctslayer. advancements ",
    "!addhistory ctslayer. playtime ",

    "!addhistory greattigergaming deaths ",
    "!addhistory greattigergaming advancements ",
    "!addhistory greattigergaming playtime ",

    "!addhistory the_rock_gaming deaths ",
    "!addhistory the_rock_gaming advancements ",
    "!addhistory the_rock_gaming playtime ",

    "!addhistory neoptolemus_ advancements ",
    "!addhistory neoptolemus_ playtime ",
    "!addhistory neoptolemus_ deaths "
]

for command in commands:
    pyperclip.copy(command)
    print(f"Copied: {command}")
    input("Press Enter to copy the next command...")
