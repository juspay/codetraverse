public class Model {
    private String name;
    private int value;
    
    public Model(String name) {
        this.name = name;
    }
    
    public void setValue(int val) {
        this.value = val;
    }
    
    public int getValue() {
        return value;
    }
}
