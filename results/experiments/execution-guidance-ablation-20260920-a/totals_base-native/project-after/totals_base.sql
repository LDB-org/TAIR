SELECT user_id, SUM(amount) AS total
FROM events
WHERE status = 'posted'
GROUP BY user_id
ORDER BY user_id ASC;
