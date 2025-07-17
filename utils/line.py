file_name = 'data/line.txt'

with open(file_name, 'r') as fnr:
    text = fnr.readlines()

text = ','.join([line.strip() for line in text])

with open(file_name, 'w') as fnw:
    fnw.write(text)