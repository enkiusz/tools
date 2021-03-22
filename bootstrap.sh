#!/bin/sh

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
