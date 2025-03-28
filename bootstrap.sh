#!/usr/bin/env sh

no_prereqs() {
	echo '# The toolset requires the following tools to be installed:'
	echo '# - stow'
	echo '# - git'
	echo '# - curl'
	echo '# - python3'
	echo '# - realpath'
	echo '# - giturlparse python module for python3'
	echo '#'
	exit 1
}

which stow >/dev/null 2>&1 || no_prereqs
which git >/dev/null 2>&1 || no_prereqs
which curl >/dev/null 2>&1 || no_prereqs
which python3 >/dev/null 2>&1 || no_prereqs
which realpath >/dev/null 2>&1 || no_prereqs
python3 -c 'import giturlparse' || no_prereqs

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

mkdir -p "$REPOS_ROOT" "$STOW_DIR"

# Get the clonerepo tool
TMPDIR=$(mktemp -d)
echo "Temporary directory will be '$TMPDIR'"

(
	cd "$TMPDIR"; export PATH="$PWD:$PATH";
	# Use redirection instead of -O beacuse curl installed from Ubuntu snap cannot write to arbitrary locations.
	# Reference: https://github.com/woutervb/snap-curl/issues/2
	# https://forum.snapcraft.io/t/classic-confinement-request-for-curl/24611
	curl https://raw.githubusercontent.com/enkiusz/tools/master/bin/clonerepo > clonerepo
	curl https://raw.githubusercontent.com/enkiusz/tools/master/bin/urlparse > urlparse
	chmod +x clonerepo urlparse
	clonerepo https://github.com/enkiusz/tools.git
)


# Create stow package
(
	cd "$REPOS_ROOT/github.com/enkiusz/tools"

	# This is needed only because we are bootstrapping an we don't have the tools
	# stowed yet in a directory available in PATH
	export PATH="$PWD/bin:$PATH"

	./makepkgs
)

# Stow tools
# Don't fold as ~/.local/{bin,lib,share} is often used by other tools and making
# it a symlink to the stow package directory might end up creating random files
# in the repo.
( cd "$STOW_DIR"; stow --no-folding tools )

echo ""
echo ""
echo "#"
echo "#"
echo "# Bootstrap completed"
echo "# You need to modify your PATH variable to include the $HOME/.local/bin directory"
echo "# For example, put the following in your $HOME/.profile"
echo "export PATH=\"\$PATH:\$HOME/.local/bin\""
echo ""
echo "In more recent Linux distributions this directory is added to the PATH automatically, so you can try"
echo "to logout and login again and see if the PATH variable contains the \"\$PATH:\$HOME/.local/bin\" directory"
echo ""
echo ""

rm -r "$TMPDIR"
