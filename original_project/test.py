import os

def count_exe_time():
	path = "Output/RE_SQL/postgres_r/"

	print("-----Re SQL analyze-----")
	# Get list of all folders in the directory
	folders = os.listdir(path)

	for folder in folders:
		# Get list of all files in the directory
		files = os.listdir(os.path.join(path, folder))	
		print(f"Folder: {folder}")
		print(f"Number of files: {len(files)}")

		# Filter files that end with .err
		err_files = [f for f in files if f.endswith('.err')]

		# Read and print the content of each .err file
		max_time = 0
		sum_time = 0
		for err_file in err_files:
			with open(os.path.join(path + folder, err_file), 'r') as file:
				content = file.read()
				# print(f"Content of {err_file}:\n{content}\n")
				content = content.split(" ")
				if content[2] == "":
					print("Error in file: ", err_file)
				max_time = int(content[2]) if int(content[2]) > max_time else max_time
				sum_time += int(content[2])
				if int(content[2]) > 10:
					print(f"Time of {err_file}: {content[2]}")
		print(f"Max time: {max_time}")
		print(f"Sum time: {sum_time}")
		print("---------------------------------")

def count_mv_exe_time(mv_nodes):
	path = "MV/postgres_r/"


	# print("-----MV analyze-----")
	# Get list of all folders in the directory
	files = os.listdir(path)
	# Filter files that end with .err
	err_files = [f for f in files if f.endswith('.err')]

	# Read and print the content of each .err file
	max_time = 0
	sum_time = 0
	for err_file in err_files:
		for node_name in mv_nodes:
			# print(f"Node name: {node_name}")
			# print(f"Err file: {err_file}")
			if node_name + "." in err_file:
				with open(os.path.join(path, err_file), 'r') as file:
					content = file.read()
					# print(f"Content of {err_file}:\n{content}\n")
					content = content.split(" ")
					max_time = int(content[2]) if int(content[2]) > max_time else max_time
					sum_time += int(content[2])
					if int(content[2]) > 15:
						print(f"Time of {err_file}: {content[2]}")
				break

	print(f"  Max time: {max_time}")
	print(f"  Sum time: {sum_time}")
	print("---------------------------------")


if __name__ == "__main__":
	count_exe_time()
	