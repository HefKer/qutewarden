{
  description = "qutewarden: Bitwarden (rbw) userscript for qutebrowser";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      packages = forAllSystems (pkgs: {
        qutewarden = pkgs.python3Packages.buildPythonApplication {
          pname = "qutewarden";
          version = "0.1.0";
          pyproject = true;
          src = self;

          build-system = [ pkgs.python3Packages.hatchling ];
          dependencies = [ pkgs.python3Packages.tldextract ];

          nativeCheckInputs = [ pkgs.python3Packages.pytestCheckHook ];
          # Browser tests need Chromium; the packaging test builds a wheel itself.
          disabledTestMarks = [ "browser" ];
          disabledTestPaths = [ "tests/test_packaging.py" ];
          pythonImportsCheck = [ "qutewarden" ];

          meta = {
            description = "Bitwarden (rbw) userscript for qutebrowser";
            homepage = "https://github.com/HefKer/qutewarden";
            license = pkgs.lib.licenses.gpl3Plus;
            mainProgram = "qutewarden";
          };
        };
        default = self.packages.${pkgs.stdenv.hostPlatform.system}.qutewarden;
      });

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = [
            (pkgs.python3.withPackages (p: [
              p.pytest
              p.tldextract
              p.playwright
              p.hatchling
            ]))
            pkgs.rbw
          ];
          # nixpkgs' Chromium build matching the python playwright package;
          # browsers downloaded by `playwright install` don't run on NixOS.
          PLAYWRIGHT_BROWSERS_PATH = "${pkgs.playwright-driver.browsers}";
          PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS = "true";
        };
      });
    };
}
