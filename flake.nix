{
  description = "Pytorch with cuda enabled";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-25.11";
  };
  outputs =
    { self, nixpkgs }:

    let
      pkgs = import nixpkgs {
        system = "x86_64-linux";
        config.allowUnfree = true;
      };
    in
    {
      devShells."x86_64-linux".default = pkgs.mkShell {
        # UV_PYTHON = "${pkgs.python314}/bin/python";
        LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
          pkgs.stdenv.cc.cc
          pkgs.zlib
          # "/run/opengl-driver"
        ];
        packages = with pkgs; [
          python313
          python313Packages.venvShellHook
          python313Packages.tkinter
          uv
          # ruff
          # ty
        ];
        venvDir = ".venv";
        postShellHook = ''
          export UV_LINK_MODE=copy
        '';
      };
    };
}
