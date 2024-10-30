import pandas as pd
import matplotlib.pyplot as plt

# Load the CSV file
df = pd.read_csv('reliability_loss.csv')  # Replace 'your_csv_file.csv' with your actual CSV file path

# Group by loss and fast_recovery and calculate the mean time-to-complete (ttc)
avg_ttc = df.groupby(['loss', 'fast_recovery'])['ttc'].mean().unstack()

# Plot the results
plt.figure(figsize=(10, 6))
plt.plot(avg_ttc.index, avg_ttc[1], label='With Fast Recovery', marker='o')
plt.plot(avg_ttc.index, avg_ttc[0], label='Without Fast Recovery', marker='o')
plt.xlabel('Loss Rate (%)')
plt.ylabel('Average Transmission Time (seconds)')
plt.title('File Transmission Time vs Loss Rate')
plt.legend()
plt.grid(True)
# Save the plot as an image file
plt.savefig('transmission_time_vs_loss_rate.png', format='png')  # You can specify any format you like (e.g., 'jpg', 'svg')

