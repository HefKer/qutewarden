# Flake check: evaluates a home-manager configuration that uses the module
# and checks the generated config file, userscript link and key bindings.
{
  pkgs,
  home-manager,
  module,
  package,
}:
let
  hm = home-manager.lib.homeManagerConfiguration {
    inherit pkgs;
    modules = [
      module
      {
        home.username = "test";
        home.homeDirectory = "/home/test";
        home.stateVersion = "25.05";
        programs.qutebrowser.enable = true;
        programs.qutewarden = {
          enable = true;
          settings.matching.equivalent_domains = [
            [
              "example.com"
              "example.org"
            ]
          ];
          keyBindings = {
            ",p" = "fill";
            ",P" = "fill --auto-fill";
          };
        };
      }
    ];
  };
  files = hm.config.home-files;
  installed = builtins.elem package hm.config.home.packages;
in
assert installed || throw "hm-module check: package not in home.packages";
pkgs.runCommand "hm-module-check" { nativeBuildInputs = [ pkgs.python3 ]; } ''
  set -euo pipefail
  fail() { echo "FAIL: $*" >&2; exit 1; }

  link=${files}/.local/share/qutebrowser/userscripts/qutewarden
  [ -x "$link" ] || fail "userscript link missing"
  [ "$(readlink -f "$link")" = "$(readlink -f ${package}/bin/qutewarden)" ] \
    || fail "userscript link doesn't point at the package's qutewarden"

  python3 - ${files}/.config/qutewarden/config.toml <<'PY'
  import sys, tomllib
  with open(sys.argv[1], "rb") as f:
      cfg = tomllib.load(f)
  want = {"matching": {"equivalent_domains": [["example.com", "example.org"]]}}
  if cfg != want:
      sys.exit(f"FAIL: config.toml is {cfg!r}")
  PY

  conf=${files}/.config/qutebrowser/config.py
  grep -qF 'config.bind(",p", "spawn --userscript qutewarden fill", mode="normal")' "$conf" \
    || fail ",p binding missing: $(cat "$conf")"
  grep -qF 'config.bind(",P", "spawn --userscript qutewarden fill --auto-fill", mode="normal")' "$conf" \
    || fail ",P binding missing"

  touch $out
''
