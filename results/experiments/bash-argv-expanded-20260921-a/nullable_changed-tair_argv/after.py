SELECT station, COALESCE(SUM(value), 0) AS total
FROM readings
WHERE value IS NOT NULL
GROUP BY station
HAVING SUM(value) IS NOT NULL
ORDER BY station ASC;
