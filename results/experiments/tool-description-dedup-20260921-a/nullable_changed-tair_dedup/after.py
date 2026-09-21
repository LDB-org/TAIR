SELECT station, COALESCE(SUM(value), 0) AS total
FROM readings
WHERE value IS NOT NULL
GROUP BY station
HAVING COUNT(value) > 0
ORDER BY station ASC;
