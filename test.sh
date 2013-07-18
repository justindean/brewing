#!/usr/bin/env sh

for i in `find recipes -name *.xml -mmin -30`;do python recipe_file_cleanup.py $i; done
ls recipes/
for i in `find recipes -name *.clean -mmin -10`; do git add $1; done
git commit -a -m "Travis-CI Checking in updated recipe files"
git push
#test
exit 0
