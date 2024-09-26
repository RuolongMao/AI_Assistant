import React, { useState } from 'react';
import './App.css';
import Chart from './Chart';
import Dropzone from 'react-dropzone';
import { csvParse, autoType } from 'd3-dsv';
import DataPreview from './DataPreview';

function App() {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [dataPreviewVisible, setDataPreviewVisible] = useState(true);
  const [data, setData] = useState(null);

  const handleSend = async () => {
    if (inputValue.trim()) {
      setMessages((prevMessages) => [
        ...prevMessages,
        { sender: 'user', text: inputValue },
      ]);

      setMessages((prevMessages) => [
        ...prevMessages,
        { sender: 'bot', text: 'Processing...', loading: true },
      ]);

      try {
        const response = await fetch('http://localhost:8000/query', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ prompt: inputValue }),
        });

        const result = await response.json();

        setMessages((prevMessages) =>
          prevMessages.filter((msg) => !msg.loading)
        );

        if (response.ok) {
          if (result.response) {
            setMessages((prevMessages) => [
              ...prevMessages,
              {
                sender: 'bot',
                type: 'chart',
                spec: result.response,
                description: result.summary || 'Here is the chart based on your request.',
              },
            ]);
          } else if (result.message) {
            setMessages((prevMessages) => [
              ...prevMessages,
              { sender: 'bot', text: result.message },
            ]);
          } else {
            setMessages((prevMessages) => [
              ...prevMessages,
              { sender: 'bot', text: 'Unable to process your request.' },
            ]);
          }
        } else {
          setMessages((prevMessages) => [
            ...prevMessages,
            { sender: 'bot', text: result.detail || 'An error occurred.' },
          ]);
        }
      } catch (error) {
        setMessages((prevMessages) => [
          ...prevMessages,
          { sender: 'bot', text: 'An error occurred while processing your request.' },
        ]);
      }

      setInputValue('');
    }
  };

  const handleFileDrop = (acceptedFiles) => {
    const file = acceptedFiles[0];

    if (file && file.name.endsWith('.csv')) {
      const reader = new FileReader();

      reader.onload = () => {
        const text = reader.result;
        const parsedData = csvParse(text, autoType);
        setData(parsedData);
        setDataPreviewVisible(true);
        setErrorMessage('');

        const formData = new FormData();
        formData.append('file', file);

        fetch('http://localhost:8000/upload_data', {
          method: 'POST',
          body: formData,
        })
          .then((response) => {
            if (response.ok) {
              return response.json();
            } else {
              throw new Error('Failed to upload file.');
            }
          })
          .then((data) => {
            // Optionally display a success message
          })
          .catch((error) => {
            setErrorMessage('Error uploading file: ' + error.message);
          });
      };

      reader.readAsText(file);
    } else {
      setErrorMessage('Please upload a valid CSV file.');
    }
  };

  return (
    <div className="App">
      <h2 className="chat-title">Data Visualization AI Assistant</h2>

      <div className="file-upload">
        <Dropzone onDrop={handleFileDrop} accept=".csv">
          {({ getRootProps, getInputProps }) => (
            <div {...getRootProps()} className="dropzone">
              <input {...getInputProps()} />
              <p>Drag and drop a CSV file here, or click to select a file</p>
            </div>
          )}
        </Dropzone>
        {errorMessage && <p className="error">{errorMessage}</p>}
      </div>

      {data && (
        <DataPreview
          data={data}
          dataPreviewVisible={dataPreviewVisible}
          onToggle={() => setDataPreviewVisible(!dataPreviewVisible)}
        />
      )}

      <div className="chat-window">
        <div className="chat-history">
          {messages.map((message, index) => (
            <div key={index} className={`message-wrapper ${message.sender}`}>
              {message.sender === 'bot' && (
                <img
                  className="avatar"
                  src={`${process.env.PUBLIC_URL}/media/logo512.png`}
                  alt="Bot Avatar"
                />
              )}
              <div className={`message ${message.sender}`}>
                {message.loading ? (
                  <span>Loading...</span>
                ) : message.type === 'chart' ? (
                  <>
                    <Chart spec={message.spec} data={data} />
                    <p>{message.description}</p>
                  </>
                ) : (
                  <span>{message.text}</span>
                )}
              </div>
              {message.sender === 'user' && (
                <img
                  className="avatar"
                  src={`${process.env.PUBLIC_URL}/media/logo512.png`}
                  alt="User Avatar"
                />
              )}
            </div>
          ))}
        </div>
      </div>
      <div className="chat-input">
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={(e) => (e.key === 'Enter' ? handleSend() : null)}
          placeholder="Type your message here"
        />
        <button onClick={handleSend}>Send</button>
      </div>
    </div>
  );
}

export default App;
