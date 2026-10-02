import sys
import os
import csv



ilp_types =  ["normal", "bigsubs", "utility_capacity", "utility", "frequency"]

input_folder = "Output/"

## command line argument handler
if len(sys.argv) < 2:
	print(f"Usage: {sys.argv[0]} <ILP type>")
	print("ILP types :")
	for ilp in ilp_types:
		print(f"	{ilp}")
else:
	match sys.argv[2]:
		case "normal":
			input_folder += "normal"
		case "bigsubs":
			input_folder += "bigsubs"
		case "utility_capacity":
			input_folder += "proposed_u_b"
		case "utility":
			input_folder += "proposed_u"
		case "frequency":
			input_folder += "proposed_f"
		case _:
			print("Non valid argument")
			exit(0)

print(input_folder)

leaf = sys.argv[1].split("/")[-1].split(".")[0]

for filename in os.listdir(input_folder):
	if not filename.endswith(".csv") or filename != "mv_y_list.csv":
		continue
	print(filename)
	with open(os.path.join(input_folder, filename), "r") as csv_file:
		lines = csv.reader(csv_file)
		modified_lines = []
		for line in lines:
			if leaf in line:
				line.pop(line.index(leaf))
			modified_lines.append(",".join(line))
	modified_lines.append("")
	with open(os.path.join(input_folder, filename), 'w', newline='') as file:
		file.write("\n".join(modified_lines))