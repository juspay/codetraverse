import java.lang.Override;
import java.lang.Deprecated;
import org.junit.Test;

public class ExtendedProcessor extends BaseClass implements IProcessor {
    
    @Deprecated
    public static final String VERSION = "1.0.0";
    
    private String result;
    
    public ExtendedProcessor() {
        super();
    }
    
    @Override
    @Test
    public void process(String data) {
        baseMethod();
        this.result = "Processed: " + data;
    }
    
    @Override
    public String getResult() {
        return result;
    }
    
    @Override
    public boolean isValid() {
        return super.isValid() && result != null;
    }
    
    public void processWithCallback(String data, Callback callback) {
        process(data);
        callback.onComplete(result);
    }
    
    public interface Callback {
        void onComplete(String result);
    }
}
