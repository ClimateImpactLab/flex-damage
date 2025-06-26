// Country name lookup utility using REST Countries API
// Caches results to avoid repeated API calls

interface CountryData {
  name: {
    common: string;
    official: string;
  };
}

// Cache to store country names to avoid repeated API calls
const countryNameCache: { [iso: string]: string } = {};

/**
 * Get country name from ISO code using REST Countries API
 * Uses caching to minimize API calls
 */
export const getCountryName = async (isoCode: string): Promise<string> => {
  if (!isoCode) return isoCode;
  
  console.log(`Getting country name for: ${isoCode}`);
  
  // Return cached result if available
  if (countryNameCache[isoCode]) {
    console.log(`Found cached name for ${isoCode}: ${countryNameCache[isoCode]}`);
    return countryNameCache[isoCode];
  }
  
  // Fetch individual country name directly
  try {
    console.log(`Fetching data for ${isoCode}...`);
    const response = await fetch(`https://restcountries.com/v3.1/alpha/${isoCode}`);
    if (response.ok) {
      const data: CountryData[] = await response.json();
      if (data && data.length > 0 && data[0].name?.common) {
        countryNameCache[isoCode] = data[0].name.common;
        console.log(`Successfully cached ${isoCode}: ${data[0].name.common}`);
        return data[0].name.common;
      }
    }
  } catch (error) {
    console.warn(`Failed to fetch country name for ${isoCode}:`, error);
  }
  
  // Fallback to ISO code
  countryNameCache[isoCode] = isoCode;
  console.log(`Using fallback for ${isoCode}: ${isoCode}`);
  return isoCode;
};

/**
 * Preload country names for a list of ISO codes
 * Useful for preloading data when component mounts
 */
export const preloadCountryNames = async (isoCodes: string[]): Promise<void> => {
  const uncachedCodes = isoCodes.filter(iso => iso && !countryNameCache[iso]);
  if (uncachedCodes.length === 0) return;
  
  console.log(`Preloading country names for:`, uncachedCodes);
  
  // Fetch all uncached countries in parallel
  const promises = uncachedCodes.map(async (isoCode) => {
    try {
      console.log(`Fetching data for ${isoCode}...`);
      const response = await fetch(`https://restcountries.com/v3.1/alpha/${isoCode}`);
      if (response.ok) {
        const data: CountryData[] = await response.json();
        if (data && data.length > 0 && data[0].name?.common) {
          countryNameCache[isoCode] = data[0].name.common;
          console.log(`Successfully cached ${isoCode}: ${data[0].name.common}`);
        } else {
          countryNameCache[isoCode] = isoCode;
          console.log(`No name found for ${isoCode}, using ISO code`);
        }
      } else {
        countryNameCache[isoCode] = isoCode;
        console.log(`API error for ${isoCode}, using ISO code`);
      }
    } catch (error) {
      console.warn(`Failed to fetch country name for ${isoCode}:`, error);
      countryNameCache[isoCode] = isoCode;
    }
  });
  
  await Promise.all(promises);
  console.log(`Preload completed. Cache now contains:`, Object.keys(countryNameCache).length, 'entries');
};

/**
 * Get cached country name (synchronous)
 * Returns ISO code if not cached
 */
export const getCachedCountryName = (isoCode: string): string => {
  return countryNameCache[isoCode] || isoCode;
};

/**
 * Clear the country name cache
 */
export const clearCountryNameCache = (): void => {
  Object.keys(countryNameCache).forEach(key => delete countryNameCache[key]);
}; 