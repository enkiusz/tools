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

echo Configuration:
echo "Repos will be cloned into '$REPOS_ROOT'"
echo "Packages will be stowed inside '$STOW_DIR"

mkdir "$REPOS_ROOT"
mkdir "$STOW_DIR"

if [ "$(uname)" == "Darwin" ]; then

	echo "#"
	echo "# Homebrew installation:"
	echo "#"

	which -s brew || /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)"

	# Coreutils is needed for the realpath tool
	brew install stow coreutils

elif [ "$(uname)" == "Linux" ]; then

	sudo apt install -y stow git curl

fi

# Get the clonerepo tool
TMPDIR=$(mktemp -d)
echo "Temporary directory will be '$TMPDIR'"

# Get the urlparse dependency
pip3 install giturlparse

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
