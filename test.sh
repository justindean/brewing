#!/usr/bin/env sh

for i in `find recipes -name *.xml -mmin -30`;do python recipe_file_cleanup.py $i && git add $i; done
ls recipes/
git push
#test
exit 0
