{ stdenv, pkgs, ... }: stdenv.mkDerivation rec {
  version = "1.0";
  name = "enkiusz-tools-${version}";

  src = ./.;

  nativeBuildInputs = [];
  buildInputs = [];
  propagatedBuildInputs = [ pkgs.python3 ];

  buildPhase = "";

  installPhase = ''
    mkdir -p $out/bin
    for script in bin/*; do
        install $script -m 0755 $out/bin/$(basename "$script")
    done
  '';

  }
