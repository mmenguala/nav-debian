#!/bin/bash

set -e

# Ensure latest NAV code is built
mydir=$(dirname $0)
"$mydir/build.sh"
cd /source


exec django-admin runserver 0.0.0.0:80
