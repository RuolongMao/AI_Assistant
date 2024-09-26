import React from 'react';
import './DataPreview.css';

const DataPreview = ({ data, dataPreviewVisible, onToggle }) => {
  return (
    <div className="table-preview">
      <h3>Data Preview</h3>
      <button className="close-button" onClick={onToggle}>
        {dataPreviewVisible ? 'Hide Table Preview' : 'Show Table Preview'}
      </button>
      {dataPreviewVisible && (
        <table>
          <thead>
            <tr>
              {Object.keys(data[0]).map((key) => (
                <th key={key}>{key}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.slice(0, 10).map((row, index) => (
              <tr key={index}>
                {Object.values(row).map((value, idx) => (
                  <td key={idx}>{value !== null ? value.toString() : ''}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

export default DataPreview;
