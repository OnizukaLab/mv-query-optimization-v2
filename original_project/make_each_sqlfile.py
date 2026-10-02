import os

def save_sql_files(input_folder, output_folder):
	# Ensure the output folder exists
	os.makedirs(output_folder, exist_ok=True)
	num = 0
	# Iterate through all files in the input folder
	for path, subdirs, files in os.walk(input_folder):
		out_dir = path.split('/')[-2:]
		if out_dir[-1] == "job":
			out_dir = out_dir[-1]
		else:
			out_dir = '/'.join(out_dir)
		out_dir = output_folder+ "/" + out_dir
		for name in files:
			input_file = os.path.join(path, name)
			output_file = os.path.join(out_dir, name)
			if input_file.endswith(".sql"):
				# create dirs
				if not os.path.exists(out_dir):
					os.makedirs(out_dir)
				# copies files into output folder
				with open(input_file, 'r') as sql_file:
					data = sql_file.read()
					sql_file.close()
				with open(output_file, "w+") as out:
					out.write(data)
				num+=1
	print(num)

if __name__ == "__main__":
	# Input folder containing % folders with .sql files
	input_folder = "dataset/redbench/imdb/benchmarks"
	# Output folder to save queries
	output_folder = "dataset/RED_SQL"

	save_sql_files(input_folder, output_folder)