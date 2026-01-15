import { useRef } from 'react';
import './ImageUpload.css';

export default function ImageUpload({ images, onImagesChange }) {
  const fileInputRef = useRef(null);

  const handleFileSelect = async (e) => {
    const files = Array.from(e.target.files);
    await processFiles(files);
  };

  const handleDrop = async (e) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files).filter((file) => file.type.startsWith('image/'));
    await processFiles(files);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
  };

  const processFiles = async (files) => {
    const newImages = [];

    for (const file of files) {
      if (!file.type.startsWith('image/')) continue;

      // Convert to base64
      const base64 = await fileToBase64(file);
      newImages.push({
        data: base64,
        name: file.name,
        type: file.type,
      });
    }

    onImagesChange([...images, ...newImages]);
  };

  const fileToBase64 = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  };

  const removeImage = (index) => {
    onImagesChange(images.filter((_, i) => i !== index));
  };

  return (
    <div className='image-upload'>
      {images.length > 0 && (
        <div className='image-previews'>
          {images.map((image, index) => (
            <div key={index} className='image-preview'>
              <img src={image.data} alt={image.name} />
              <button type='button' className='remove-image' onClick={() => removeImage(index)} title='Remove image'>
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      <div className='upload-area' onDrop={handleDrop} onDragOver={handleDragOver} onClick={() => fileInputRef.current?.click()}>
        <svg width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'>
          <path d='M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4' />
          <polyline points='17 8 12 3 7 8' />
          <line x1='12' y1='3' x2='12' y2='15' />
        </svg>
        <span>Click or drag images here</span>
      </div>

      <input ref={fileInputRef} type='file' accept='image/*' multiple onChange={handleFileSelect} style={{ display: 'none' }} />
    </div>
  );
}
