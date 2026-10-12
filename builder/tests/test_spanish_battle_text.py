import importlib.util
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("localize_spanish", ROOT / "tools/localize_spanish.py")
localization = importlib.util.module_from_spec(spec)
spec.loader.exec_module(localization)


class SpanishBattleTextTests(unittest.TestCase):
    def setUp(self):
        names = ["sText_PkmnTeamGainedEXP", "sText_WildPkmnPrefix"]
        names += ["sText_FoePkmnPrefix" + suffix for suffix in ("", "2", "3", "4")]
        self.source = "\n".join('static const u8 ' + name + '[] = _("original");' for name in names)

    def test_translation_and_separator(self):
        result = localization.localize_port_battle_text(self.source)
        self.assertIn(r'_("¡El resto del equipo ganó\npuntos de experiencia!\p")', result)
        prefixes = re.findall(r'sText_(?:Wild|Foe)PkmnPrefix\d?\[\] = _\("([^"]+)"\)', result)
        self.assertEqual(len(prefixes), 5)
        for prefix in prefixes:
            self.assertTrue(prefix.endswith(" "))
            self.assertFalse(prefix.startswith(" "))
            self.assertIn(" LOTAD", prefix + "LOTAD")
        self.assertEqual(localization.localize_port_battle_text(result), result)

    def test_missing_definition_is_rejected(self):
        with self.assertRaises(ValueError):
            localization.localize_port_battle_text("")

    @unittest.skipUnless(shutil.which("cc"), "requires a host C compiler")
    def test_clock_accents_use_game_glyphs(self):
        source = (ROOT / "3ds_port/src/3ds_bottom_ui.c").read_text()
        start = source.index("static const u8 *Ascii(")
        end = source.index("static const u8 *Number(", start)
        harness = '''
#include <assert.h>
#include <stdint.h>
typedef uint8_t u8;
#define CHAR_N_TILDE 0x14
#define CHAR_I_ACUTE 0x5A
#define CHAR_A 0xBB
#define CHAR_a 0xD5
#define CHAR_0 0xA1
#define CHAR_SLASH 0xBA
#define CHAR_HYPHEN 0xAE
#define CHAR_PERIOD 0xAD
#define CHAR_COLON 0xF0
#define CHAR_EXCL_MARK 0xAB
#define CHAR_QUESTION_MARK 0xAC
#define CHAR_SGL_QUOTE_RIGHT 0xB4
#define CHAR_e_ACUTE 0x1B
#define CHAR_SPACE 0
#define EOS 0xFF
'''
        harness += source[start:end]
        harness += '''
int main(void) {
    const u8 *morning = Ascii("MAÑANA");
    assert(morning[2] == CHAR_N_TILDE && morning[6] == EOS);
    const u8 *day = Ascii("DÍA");
    assert(day[1] == CHAR_I_ACUTE && day[3] == EOS);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            code = folder / "clock.c"
            binary = folder / "clock"
            code.write_text(harness)
            subprocess.run(["cc", "-std=c99", "-Wall", "-Wextra", "-Werror",
                            str(code), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
