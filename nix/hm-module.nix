# home-manager module: `programs.qutewarden` (docs/spec-v2.md, "home-manager module").
self:
{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.programs.qutewarden;
  toml = pkgs.formats.toml { };
in
{
  options.programs.qutewarden = {
    enable = lib.mkEnableOption "qutewarden, the Bitwarden (rbw) userscript for qutebrowser";

    package = lib.mkOption {
      type = lib.types.package;
      default = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
      defaultText = lib.literalExpression "qutewarden.packages.\${system}.default";
      description = "The qutewarden package to install and link as a userscript.";
    };

    settings = lib.mkOption {
      type = toml.type;
      default = { };
      example = lib.literalExpression ''
        {
          matching.equivalent_domains = [ [ "example.com" "example.org" ] ];
        }
      '';
      description = ''
        qutewarden settings, written to `$XDG_CONFIG_HOME/qutewarden/config.toml`.
        Empty settings write no file.
      '';
    };

    keyBindings = lib.mkOption {
      type = lib.types.attrsOf lib.types.str;
      default = { };
      example = {
        ",p" = "fill";
        ",P" = "fill --auto-fill";
      };
      description = ''
        qutebrowser normal-mode bindings: key to qutewarden arguments, each added to
        `programs.qutebrowser.keyBindings.normal` as `spawn --userscript qutewarden <arguments>`.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    home.packages = [ cfg.package ];

    # `spawn --userscript` doesn't search PATH, only the userscripts directories.
    xdg.dataFile."qutebrowser/userscripts/qutewarden".source = lib.getExe cfg.package;

    xdg.configFile."qutewarden/config.toml" = lib.mkIf (cfg.settings != { }) {
      source = toml.generate "qutewarden-config.toml" cfg.settings;
    };

    programs.qutebrowser.keyBindings.normal = lib.mapAttrs (
      _: args: "spawn --userscript qutewarden ${args}"
    ) cfg.keyBindings;
  };
}
