from src.char.BaseChar import BaseChar


class Suoming(BaseChar):
    """Suoming auto combat (5-star Electro Sword — patch 3.7).

    Kit details are not published yet (prydwen.gg lists the character for
    patch 3.7 with skills "to be added soon"), so this class deliberately
    runs the conservative default rotation from BaseChar:
    intro -> echo -> liberation -> resonance (or heavy on full forte) -> switch.

    Replace do_perform with a tuned rotation once the kit is finalized.
    """

    def do_perform(self):
        super().do_perform()
