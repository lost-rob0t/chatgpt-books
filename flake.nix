{
  description = "Org-first technical-book publishing environment";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs = { self, nixpkgs }: let
    systems = [ "x86_64-linux" "aarch64-linux" ];
    forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f (import nixpkgs { inherit system; }));
  in {
    devShells = forAllSystems (pkgs: { default = pkgs.mkShell {
      packages = with pkgs; [ emacs pandoc graphviz epubcheck python3 python3Packages.matplotlib gnumake ];
    }; });
  };
}
