stress-ng --cpu 2 --timeout 5s
for i in {1..100}; do
echo $i
sleep 0.5
done