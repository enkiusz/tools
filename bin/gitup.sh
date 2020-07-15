#!/bin/bash

## Category: Daily/maintenance
## Shortdesc: Pull from origin in all cloned repositories

readonly REPOS_BASE="${REPOS_BASE:-$HOME/repos}"

# Colors
readonly BLACK=0 RED=1 GREEN=2 YELLOW=2 BLUE=4 MAGENTA=5 CYAN=6 WHITE=7

titleon()
{
    tput setf $YELLOW
}
titleoff()
{
    tput sgr0
}

find "$REPOS_BASE" -name '.git' -type d | while read gitdir; do
    repo_dir=$(dirname "$gitdir")
    titleon; echo "Maintaining repo in '$repo_dir'"; titleoff
    pushd "$repo_dir" > /dev/null
    # Get rid of default message printed when remote repository was not changed.
    git pull | grep -v -F -e 'Already up to date.'
    git status -s
    popd > /dev/null
done

