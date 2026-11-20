"""
test_invitations.py — D-200

Run: python test_invitations.py

The cases that would fail quietly: a code from the address that is not
cleaned before it reaches the database, a generated code with characters that
read the same (0/O, 1/I), a name with accents that breaks the code, and a link
that loses the code or the UTM tags.
"""

import re
import sys

import invitations as I

failures = []


def check(name, cond):
    if not cond:
        failures.append(name)


# normalise: the address is visitor-controlled
check("upper-cased and trimmed", I.normalise("  beta-prabin-7k3q ") == "BETA-PRABIN-7K3Q")
check("empty is None", I.normalise("") is None and I.normalise(None) is None)
check("too short is None", I.normalise("AB") is None)
check("too long is None", I.normalise("A" * 41) is None)
check("no SQL or URL characters", I.normalise("BETA'; DROP") is None and I.normalise("a b c d") is None
      and I.normalise("BETA%20X") is None)
check("leading dash refused", I.normalise("-BETA-X") is None)

# new_code
codes = {I.new_code("Prabin") for _ in range(200)}
check("format BETA-NAME-XXXX", all(re.fullmatch(r"BETA-PRABIN-[A-Z0-9]{4}", c) for c in codes))
check("no ambiguous characters in the suffix",
      not any(set(c[-4:]) & set("0O1IL") for c in codes))
check("random suffix", len(codes) > 190)
check("accents dropped", I.new_code("Hélène Müller").startswith("BETA-HELENEMULLER-"))
check("name cut to 12", len(I.new_code("A very long company name SRL").split("-")[1]) == 12)
check("empty name still a code", I.new_code("").startswith("BETA-INVITE-"))
check("a generated code passes normalise", all(I.normalise(c) == c for c in codes))

# invite_link
link = I.invite_link("BETA-PRABIN-7K3Q")
check("link carries the code", "code=BETA-PRABIN-7K3Q" in link)
check("link carries the UTM tags",
      "utm_source=linkedin" in link and "utm_medium=dm" in link and "utm_campaign=beta" in link)
check("link goes to the free check", link.startswith("https://check.recosa.eu/?"))

if failures:
    print("FAILED:\n  " + "\n  ".join(failures))
    sys.exit(1)
print("All invitation tests passed.")
