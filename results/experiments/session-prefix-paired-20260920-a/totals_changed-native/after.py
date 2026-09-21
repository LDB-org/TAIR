SELECT user_id, SUM(amount) AS total
FROM events
WHERE status = 'posted'
GROUP BY user_id
HAVING SUM(amount) > 0
ORDER BY user_id ASC;
