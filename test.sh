#!/usr/bin/env sh

for i in `find recipes -name *.xml -mmin -30`;do python recipe_file_cleanup.py $i; done
exit 0
