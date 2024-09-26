import React from 'react';
import { VegaLite } from 'react-vega';

const Chart = ({ spec, data }) => {
  const chartData = {
    data: data,
  };

  return (
    <div className="chart-container">
      <VegaLite spec={spec} data={chartData} actions={false} />
    </div>
  );
};

export default Chart;
