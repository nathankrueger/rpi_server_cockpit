TIME=30

stress-ng --cpu 2 --timeout ${TIME}s&

for ((i = 1; i <= $TIME; i++)) do
    echo $i
    sleep 1
done