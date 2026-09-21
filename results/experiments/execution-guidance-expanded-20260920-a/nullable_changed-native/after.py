SELECT station, COALESCE(SUM(value), 0) AS total
FROM readings
GROUP BY station
HAVING COUNT(value) > 0 AND SUM(value) <= 0
ORDER BY station ASC;
