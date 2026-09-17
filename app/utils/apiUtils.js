export async function fetchWithRetry(url, options, maxRetries = 10, baseDelay = 500) {
    let attempt = 0;

    while (attempt < maxRetries) {
        try {
            const response = await fetch(url, options);

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Request failed');
            }

            return await response.json(); // Return the successful response data
        } catch (error) {
            attempt++;
            if (attempt >= maxRetries) {
                throw new Error('Server cannot be reached');
            }

            // Exponential backoff delay
            const delay = baseDelay * Math.pow(2, attempt);
            await new Promise((resolve) => setTimeout(resolve, delay));
        }
    }
}