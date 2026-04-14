{
  description = "Industry report generator for Dallas College LMIC";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
    git-hooks = {
      url = "github:cachix/git-hooks.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    inputs@{ flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [
        inputs.git-hooks.flakeModule
      ];

      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];

      perSystem =
        {
          config,
          pkgs,
          ...
        }:
        let
          python = pkgs.python313;
        in
        {
          pre-commit = {
            check.enable = true;
            settings = {
              hooks = {
                ruff.enable = true;
                ruff-format.enable = true;
                trim-trailing-whitespace.enable = true;
                end-of-file-fixer.enable = true;
                check-merge-conflicts.enable = true;
                check-added-large-files = {
                  enable = true;
                  args = [ "--maxkb=5000" ];
                };
                check-toml.enable = true;
                check-python.enable = true;
                nixfmt-rfc-style.enable = true;
                deadnix = {
                  enable = true;
                  settings.edit = true;
                };
                statix.enable = true;
              };
            };
          };

          devShells.default = pkgs.mkShell {
            buildInputs = [
              python
              pkgs.uv
              pkgs.stdenv.cc.cc.lib
              pkgs.zlib
            ]
            ++ (with pkgs.python313Packages; [
              debugpy
              python-lsp-server
              python-lsp-ruff
              pylsp-mypy
            ])
            ++ config.pre-commit.settings.enabledPackages;

            env = {
              UV_PYTHON_DOWNLOADS = "never";
              UV_PYTHON = python.interpreter;
            };

            shellHook = ''
              ${config.pre-commit.installationScript}

              echo "🐍 Python Development Environment"
              echo "Python: ${python.version}"

              unset PYTHONPATH
              export PYTHONPATH="$PWD:$PYTHONPATH"
              export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.zlib}/lib:$LD_LIBRARY_PATH"

              if [[ ! -d .venv ]]; then
                echo "Creating Python virtual environment..."
                uv venv
                uv sync
              else
                source .venv/bin/activate
                if [[ pyproject.toml -nt .venv ]]; then
                  echo "Dependencies may have changed, running uv sync..."
                  uv sync
                fi
              fi
            '';
          };
        };
    };
}
