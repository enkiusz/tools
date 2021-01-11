#!/bin/sh

#
# Configuration
#
if [ -z $REPOS_ROOT ]; then
	export REPOS_ROOT="$HOME/repos"
fi
if [ -z $STOW_DIR ]; then
	export STOW_DIR="$HOME/stow"
fi

echo "# Configuration:"
echo "# Repos will be cloned into '$REPOS_ROOT'"
echo "# Packages will be stowed inside '$STOW_DIR'"

if [ "$(uname)" == "Darwin" ]; then

	no_prereqs_darwin() {
		echo # The bootstrap script requires the following tools to be installed:
		echo # - stow
		echo # - git
		echo # - curl
		echo # - python3
		echo # - realpath
		echo # - giturlparse python module for python3
		echo #
		echo # Please use Homebrew and pip3 to install them
		exit 1
	}

	which -s stow || no_prereqs_darwin
	which -s git || no_prereqs_darwin
	which -s curl || no_prereqs_darwin
	which -s python3 || no_prereqs_darwin
	which -s realpath || no_prereqs_darwin
	python -c 'import giturlparse' || no_prereqs_darwin

elif [ "$(uname)" == "Linux" ]; then

	no_prereqs_linux() {
		echo # The toolset requires the following tools to be installed:
		echo # - stow
		echo # - git
		echo # - curl
		echo # - python3
		echo # - giturlparse python module for python3
		echo #
		exit 1
	}

	which stow >/dev/null || no_prereqs_linux
	which git >/dev/null || no_prereqs_linux
	which curl >/dev/null || no_prereqs_linux
	which python3 >/dev/null || no_prereqs_linux
	python3 -c 'import giturlparse' || no_prereqs_linux
fi

mkdir -p "$REPOS_ROOT" "$STOW_DIR"

# Get the clonerepo tool
TMPDIR=$(mktemp -d)
echo "Temporary directory will be '$TMPDIR'"

(
	cd "$TMPDIR"; export PATH="$PWD:$PATH";
	curl -O https://raw.githubusercontent.com/mgrela/tools/master/bin/clonerepo
	curl -O https://raw.githubusercontent.com/mgrela/tools/master/bin/urlparse
	chmod +x clonerepo urlparse
	clonerepo https://github.com/mgrela/tools.git
)


# Create stow package
(
	cd "$REPOS_ROOT/github.com/mgrela/tools"

	# This is needed only because we are bootstrapping an we don't have the tools
	# stowed yet in a directory available in PATH
	export PATH="$PWD/bin:$PATH"

	./makepkgs
)

# Stow tools
( cd "$STOW_DIR"; stow tools )

echo ""
echo ""
echo "#"
echo "#"
echo "# Bootstrap completed"
echo "# You need to modify your PATH variable to include the $HOME/.local/bin directory"
echo "# For example, put the following in your $HOME/.profile"
echo "export PATH=\"\$PATH:\$HOME/.local/bin\""
echo ""
echo ""

rm -r "$TMPDIR"
