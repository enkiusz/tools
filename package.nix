{ stdenv, pkgs, ... }: stdenv.mkDerivation rec {
  version = "1.0";
  name = "enkiusz-tools-${version}";

  src = ./.;

  nativeBuildInputs = [];
  buildInputs = [];
  propagatedBuildInputs = [ ( pkgs.python3.withPackages(ps: with ps; [
        (buildPythonPackage rec {
            pname = "giturlparse";
            version = "0.12.0";
            src = fetchPypi {
              inherit pname version;
              sha256 = "16l5qgc2m98yz3j4gjzx3xf20ykm73h6d5bpn68m8hyc3b1ggzy0";
            };
        })
        ]))
  ];

  buildPhase = "";

  installPhase = ''
    mkdir -p $out/bin
    for script in bin/*; do
        install $script -m 0755 $out/bin/$(basename "$script")
    done
  '';

  }
