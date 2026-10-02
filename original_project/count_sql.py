import os

def count_exe_time():
	path = "Output/SQL/postgres_r/"


	print("----- SQL analyze-----")
	# Get list of all files in the directory
	files = os.listdir(path)
	print(f"Number of files: {len(files)}")

	# Filter files that end with .err
	err_files = [f for f in files if f.endswith('.err')]

	# Read and print the content of each .err file
	max_time = 0
	sum_time = 0
	for err_file in err_files:
		# print(f"File: {err_file}")
		with open(os.path.join(path, err_file), 'r') as file:
			content = file.read()
			# print(f"Content of {err_file}:\n{content}\n")
			content = content.split(" ")
			if content[2] == "":
				print("Error in file: ", err_file)
			max_time = float(content[2]) if float(content[2]) > max_time else max_time
			sum_time += float(content[2])
			if float(content[2]) > 15:
				print(f"Time of {err_file}: {content[2]}")
	print(f"Max time: {max_time}")
	print(f"Sum time: {sum_time}")
	print("---------------------------------")

if __name__ == "__main__":
	count_exe_time()