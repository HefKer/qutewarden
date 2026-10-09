{
  description = "qutewarden: Bitwarden (rbw) userscript for qutebrowser";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    # Only for the flake check that evaluates the home-manager module.
    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      home-manager,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
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

          # Child Pythons (`sys.executable -m qutewarden.clipboard_clear`)
          # don't get the wrapper's site dirs; give them a PYTHONPATH.
          makeWrapperArgs = [
            "--prefix"
            "PYTHONPATH"
            ":"
            "${placeholder "out"}/${pkgs.python3.sitePackages}:${pkgs.python3Packages.makePythonPath [ pkgs.python3Packages.tldextract ]}"
          ];

          nativeCheckInputs = [ pkgs.python3Packages.pytestCheckHook ];
          # Browser tests need Chromium; the packaging test builds a wheel itself.
          disabledTestMarks = [ "browser" ];
          disabledTestPaths = [ "tests/test_packaging.py" ];
          pythonImportsCheck = [ "qutewarden" ];

          # The clipboard clearer is started as `sys.executable -m
          # qutewarden.clipboard_clear`, and sys.executable is the bare
          # interpreter, so it must find qutewarden through the wrapper's
          # environment. Run it that way (no args: exit 2 = module found).
          postInstallCheck = ''
            sed '$d' $out/bin/qutewarden > check-clearer.sh
            echo 'exec ${pkgs.python3.interpreter} -m qutewarden.clipboard_clear' >> check-clearer.sh
            status=0
            env -u PYTHONPATH bash check-clearer.sh || status=$?
            if [ "$status" != 2 ]; then
              echo "qutewarden.clipboard_clear can't run under the wrapper (exit $status)" >&2
              exit 1
            fi
          '';

          meta = {
            description = "Bitwarden (rbw) userscript for qutebrowser";
            homepage = "https://github.com/HefKer/qutewarden";
            license = pkgs.lib.licenses.gpl3Plus;
            mainProgram = "qutewarden";
          };
        };
        default = self.packages.${pkgs.stdenv.hostPlatform.system}.qutewarden;
      });

      homeManagerModules.default = import ./nix/hm-module.nix self;

      checks = forAllSystems (pkgs: {
        hm-module = import ./nix/hm-module-check.nix {
          inherit pkgs home-manager;
          module = self.homeManagerModules.default;
          package = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
        };
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
            pkgs.ruff
            pkgs.pyright
            # Runs qutewarden from this checkout's src/, against your real rbw.
            (pkgs.writeShellScriptBin "qutewarden-dev" ''exec python -m qutewarden "$@"'')
          ];
          # src/ on the path, so `python -c 'import qutewarden...'` and the
          # clipboard clearer child (`python -m qutewarden.clipboard_clear`) work.
          shellHook = ''
            export PYTHONPATH="$PWD/src''${PYTHONPATH:+:$PYTHONPATH}"
          '';
          # nixpkgs' Chromium build matching the python playwright package;
          # browsers downloaded by `playwright install` don't run on NixOS.
          PLAYWRIGHT_BROWSERS_PATH = "${pkgs.playwright-driver.browsers}";
          PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS = "true";
        };
      });
    };
}
