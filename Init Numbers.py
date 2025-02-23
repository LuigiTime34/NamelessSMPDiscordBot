import pyperclip

commands = [
    "!addhistory luigi_is_better deaths 31",
    "!addhistory luigi_is_better advancements 49",
    "!addhistory luigi_is_better playtime 90120",

    "!addhistory sblujay deaths 17",
    "!addhistory sblujay advancements 20",
    "!addhistory sblujay playtime 22440",

    "!addhistory kazzpyr deaths 2",
    "!addhistory kazzpyr advancements 21",
    "!addhistory kazzpyr playtime 15420",

    "!addhistory bobbilby deaths 40",
    "!addhistory bobbilby advancements 27",
    "!addhistory bobbilby playtime 44160",

    "!addhistory wizardcat1000 deaths 31",
    "!addhistory wizardcat1000 advancements 37",
    "!addhistory wizardcat1000 playtime 47640",

    "!addhistory ih8tk deaths 148",
    "!addhistory ih8tk advancements 32",
    "!addhistory ih8tk playtime 56160",

    "!addhistory salmon5117_73205 deaths 17",
    "!addhistory salmon5117_73205 advancements 39",
    "!addhistory salmon5117_73205 playtime 66660",

    "!addhistory frogloverender deaths 100",
    "!addhistory frogloverender advancements 31",
    "!addhistory frogloverender playtime 60300",

    "!addhistory sweatshirtboi16 deaths 5",
    "!addhistory sweatshirtboi16 advancements 9",
    "!addhistory sweatshirtboi16 playtime 7740",

    "!addhistory mindjames_93738 deaths 2",
    "!addhistory mindjames_93738 advancements 9",
    "!addhistory mindjames_93738 playtime 2160",

    "!addhistory car248. deaths 1",
    "!addhistory car248. advancements 20",
    "!addhistory car248. playtime 9540",

    "!addhistory ctslayer. deaths 20",
    "!addhistory ctslayer. advancements 21",
    "!addhistory ctslayer. playtime 42420",

    "!addhistory greattigergaming deaths 1",
    "!addhistory greattigergaming advancements 19",
    "!addhistory greattigergaming playtime 7140",

    "!addhistory the_rock_gaming deaths 3",
    "!addhistory the_rock_gaming advancements 47",
    "!addhistory the_rock_gaming playtime 64680",

    "!addhistory neoptolemus_ advancements 18",
    "!addhistory neoptolemus_ playtime 5940"
]

for command in commands:
    pyperclip.copy(command)
    print(f"Copied: {command}")
    input("Press Enter to copy the next command...")
