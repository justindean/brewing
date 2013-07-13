from sys import argv

f = open(argv[1], 'r')
file = f.read()
file2 = file.replace("\r\n", "")
file3 = file2.replace('>\n', '>')
file4 = file3.replace('> <', '><')
cleanfile = open(argv[1]+'.clean', 'w')
cleanfile.write(file4)
cleanfile.close()


