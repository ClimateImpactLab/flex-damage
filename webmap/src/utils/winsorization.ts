// utils/winsorization.ts

export function calculatePercentile(values: number[], percentile: number): number {
  const sorted = [...values].sort((a, b) => a - b);
  const index = (percentile / 100) * (sorted.length - 1);
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  
  if (lower === upper) {
    return sorted[lower];
  }
  
  const weight = index - lower;
  return sorted[lower] * (1 - weight) + sorted[upper] * weight;
}

export function winsorizeData(
  values: number[], 
  lowerPercentile: number = 5, 
  upperPercentile: number = 95
): number[] {
  if (values.length === 0) return values;
  
  const lowerBound = calculatePercentile(values, lowerPercentile);
  const upperBound = calculatePercentile(values, upperPercentile);
  
  return values.map(value => {
    if (value < lowerBound) return lowerBound;
    if (value > upperBound) return upperBound;
    return value;
  });
}

export function winsorizeMap(
  dataMap: { [iso: string]: number },
  lowerPercentile: number = 5,
  upperPercentile: number = 95
): { [iso: string]: number } {
  const values = Object.values(dataMap);
  if (values.length === 0) return dataMap;
  
  const lowerBound = calculatePercentile(values, lowerPercentile);
  const upperBound = calculatePercentile(values, upperPercentile);
  
  const winsorizedMap: { [iso: string]: number } = {};
  for (const [iso, value] of Object.entries(dataMap)) {
    if (value < lowerBound) {
      winsorizedMap[iso] = lowerBound;
    } else if (value > upperBound) {
      winsorizedMap[iso] = upperBound;
    } else {
      winsorizedMap[iso] = value;
    }
  }
  
  return winsorizedMap;
} 